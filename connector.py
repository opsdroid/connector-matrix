import re
import logging

import aiohttp

from opsdroid.connector import Connector
from opsdroid.message import Message

from matrix_api_async import AsyncHTTPAPI
from .html_cleaner import clean
from matrix_client.errors import MatrixRequestError


_LOGGER = logging.getLogger(__name__)

__all__ = ['ConnectorMatrix']


def trim_reply_fallback_text(text):
    # Copyright (C) 2018 Tulir Asokan
    # Borrowed from https://github.com/tulir/mautrix-telegram/blob/master/mautrix_telegram/formatter/util.py
    # Having been given explicit permission to include it "under the terms of any OSI approved licence"
    # https://matrix.to/#/!FPUfgzXYWTKgIrwKxW:matrix.org/$15365871364925maRqg:maunium.net

    if not text.startswith("> ") or "\n" not in text:
        return text
    lines = text.split("\n")
    while len(lines) > 0 and lines[0].startswith("> "):
        lines.pop(0)
    return "\n".join(lines).strip()


def parse_room_config(config):
    """
    This method provides backwards compatibility with the previous room
    list as dict format by transforming dicts like `{"main": "#myroom:matrix.org"}` into
    `{"main": {"alias": "#myroom:matrix.org"}}`.
    """
    new_rooms = {}
    for name, room in config["rooms"].items():
        if isinstance(room, str):
            new_rooms[name] = {'alias': room}
        elif isinstance(room, dict):
            new_rooms[name] = room
        else:
            raise TypeError("Elements of the room config dictionary must be strings or dicts")
    return new_rooms


class ConnectorMatrix(Connector):
    def __init__(self, config):
        # Init the config for the connector
        self.name = "ConnectorMatrix"  # The name of your connector

        # Config parseing
        self.config = config  # The config dictionary to be accessed later
        self.rooms = config.get('rooms', None)
        if not self.rooms:
            self.rooms = {'main': {'alias': config['room']}}
        else:
            rooms = parse_room_config(config)
        self.mxid = config['mxid']
        self.nick = config.get('nick', None)
        self.homeserver = config.get('homeserver', "https://matrix.org")
        self.password = config['password']
        self.room_specific_nicks = config.get("room_specific_nicks", False)

        # Internal
        self.room_ids = {}
        self.default_room = self.rooms['main']['alias']  # TODO: Delete this?

    @property
    def filter_json(self):
        return {
            "event_format": "client",
            "account_data": {
                "limit": 0,
                "types": []
            },
            "presence": {
                "limit": 0,
                "types": []
            },
            "room": {
                "rooms": [],
                "account_data": {
                    "types": []
                },
                "timeline": {
                    "limit": 10,
                    "types": ["m.room.message"]
                },
                "ephemeral": {
                    "types": []
                },
                "state": {
                    "types": []
                }
            }
        }

    async def make_filter(self, api, room_ids):
        """
        Make a filter on the server for future syncs.
        """

        fjson = self.filter_json
        for room_id in room_ids:
            fjson['room']['rooms'].append(room_id)

        resp = await api.create_filter(
            user_id=self.mxid, filter_params=fjson)

        return resp['filter_id']

    async def connect(self, opsdroid):
        # Create connection object with chat library
        session = aiohttp.ClientSession()
        mapi = AsyncHTTPAPI(self.homeserver, session)

        self.session = session
        login_response = await mapi.login(
            "m.login.password", user=self.mxid, password=self.password)
        mapi.token = login_response['access_token']
        mapi.sync_token = None

        for roomname, room in self.rooms.items():
            response = await mapi.join_room(room['alias'])
            self.room_ids[roomname] = response['room_id']
        self.connection = mapi

        # Create a filter now, saves time on each later sync
        self.filter_id = await self.make_filter(mapi, self.room_ids.values())

        # Do initial sync so we don't get old messages later.
        response = await self.connection.sync(
            timeout_ms=3000, filter='{ "room": { "timeline" : { "limit" : 1 } } }',
            set_presence="online")
        self.connection.sync_token = response["next_batch"]

        if self.nick and await self.connection.get_display_name(self.mxid) != self.nick:
            await self.connection.set_display_name(self.mxid, self.nick)

    async def listen(self, opsdroid):
        # Listen for new messages from the chat service
        while True:
            try:
                response = await self.connection.sync(
                    self.connection.sync_token,
                    timeout_ms=int(6 * 60 * 60 * 1e3),  # 6h in ms
                    filter=self.filter_id)
                _LOGGER.debug("matrix sync request returned")
                self.connection.sync_token = response["next_batch"]
                for roomid in self.room_ids.values():
                    room = response['rooms']['join'].get(roomid, None)
                    if room and 'timeline' in room:
                        for event in room['timeline']['events']:
                            if event.get("content", {}).get("body", None):
                                if event['sender'] != self.mxid:
                                    message = Message(self._parse_m_room_message(event),
                                                      await self._get_nick(roomid,
                                                                           event['sender']),
                                                      roomid, self,
                                                      raw_message=event)
                                    await opsdroid.parse(message)
            except Exception:
                _LOGGER.exception('Matrix Sync Error')

    def _parse_m_room_message(self, event):
        """
        Call this to strip out replies.
        """
        if event["content"].get("m.relates_to", {}).get("m.in_reply_to", None):
            return trim_reply_fallback_text(event['content']['body'])
        else:
            return event['content']['body']

    async def _get_nick(self, roomid, mxid):
        """
        Get the nickname of a sender depending on the room specific config
        setting.
        """
        if self.room_specific_nicks:
            try:
                return await self.connection.get_room_displayname(roomid, mxid)
            except Exception:
                # Fallback to the non-room specific one
                logging.exception("Failed to lookup room specific nick for {}".format(mxid))

        try:
            return await self.connection.get_display_name(mxid)
        except MatrixRequestError as e:
            # Log the error if it's not the 404 from the user not having a nick
            if e.code != 404:
                logging.exception("Failed to lookup nick for {}".format(mxid))
            return mxid

    async def _get_html_content(self, message, body=None, msgtype="m.text"):
        """
        Return the json representation of the message in
        "org.matrix.custom.html" format
        """
        clean_html = clean(message)

        # Markdown leaves a <p></p> around standard messages that we want to strip:
        if clean_html.startswith('<p>'):
            clean_html = clean_html[3:]
            if clean_html.endswith('</p>'):
                clean_html = clean_html[:-4]

        return {
            # Strip out any tags from the markdown to make the body
            "body": body if body else re.sub('<[^<]+?>', '', clean_html),
            "msgtype": msgtype,
            "format": "org.matrix.custom.html",
            "formatted_body": clean_html
            }

    async def respond(self, message, roomname=None):
        # Send message.text back to the chat service

        if not roomname:
            # Connector responds in the same room it received the original message
            room_id = message.room
        else:
            room_id = self.rooms[roomname]['alias']

        # Ensure we have a room id not alias
        if not room_id.startswith('!'):
            room_id = await self.connection.get_room_id(room_id)
        else:
            room_id = room_id

        # Get the msgtype to respond with based on first the global then the room config.
        send_notice = self.config.get("send_m_notice", False)
        send_notice = self.rooms[self.get_roomname(room_id)].get("send_m_notice", send_notice)
        msgtype = "m.notice" if send_notice else "m.text"

        try:
            await self.connection.send_message_event(
                room_id,
                "m.room.message",
                await self._get_html_content(message.text, msgtype=msgtype))
        except aiohttp.client_exceptions.ServerDisconnectedError:
            _LOGGER.debug("Server had disconnected, retrying send.")
            await self.connection.send_message_event(
                room_id,
                "m.room.message",
                await self._get_html_content(message.text, msgtype=msgtype))

    async def disconnect(self, opsdroid=None):
        self.session.close()

    def get_roomname(self, room):
        if room.startswith(('#', '!')):
            for connroom in self.rooms:
                if room == connroom or room == self.room_ids[connroom]:
                    return connroom

        return room
