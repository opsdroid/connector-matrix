import sys
import logging

import aiohttp
from opsdroid.connector import Connector
from opsdroid.message import Message

from .matrix_async import AsyncHTTPAPI

_LOGGER = logging.getLogger(__name__)

__all__ = ['ConnectorMatrix']


class ConnectorMatrix(Connector):
    def __init__(self, config):
        # Init the config for the connector
        self.name = "ConnectorMatrix"  # The name of your connector
        self.config = config  # The config dictionary to be accessed later
        self.rooms = config['rooms']
        self.room_ids = {}
        self.default_room = self.rooms['main']
        self.mxid = config['mxid']
        self.nick = config.get('nick', None)
        self.homeserver = config.get('homeserver', "https://matrix.org")
        self.password = config['password']

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
            response = await mapi.join_room(room)
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
                room = response['rooms']['join'].get(self.room_id, None)
                if room and 'timeline' in room:
                    for event in room['timeline']['events']:
                        if event['content']['msgtype'] == 'm.text':
                            if event['sender'] != self.mxid:
                                message = Message(event['content']['body'],
                                                  await self.connection.get_room_displayname(self.default_room,
                                                                                             event['sender']),
                                                  None, self)
                                await opsdroid.parse(message)
            except Exception as e:
                _LOGGER.exception('Matrix Sync Error')

    async def respond(self, message):
        # Send message.text back to the chat service
        await self.connection.send_message(self.room_id, message.text)

    async def disconnect(self):
        self.session.close()
