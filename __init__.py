import sys
import logging

import aiohttp
from opsdroid.connector import Connector
from opsdroid.message import Message

from .matrix_async import AsyncHTTPAPI

_LOGGER = logging.getLogger(__name__)


class ConnectorMatrix(Connector):
    def __init__(self, config):
        # Init the config for the connector
        self.name = "ConnectorMatrix"  # The name of your connector
        self.config = config  # The config dictionary to be accessed later
        self.default_room = config['room']
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

    async def make_filter(self, api, room_id):
        """
        Make a filter on the server for future syncs.
        """

        fjson = self.filter_json
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

        response = await mapi.join_room(self.default_room)
        self.room_id = response['room_id']
        self.connection = mapi

        # Create a filter now, saves time on each later sync
        self.filter_id = await self.make_filter(mapi, self.room_id)

        # Do initial sync so we don't get old messages later.
        response = await self.connection.sync(
            timeout_ms=3000, filter='{ "room": { "timeline" : { "limit" : 1 } } }',
            set_presence="online")
        self.connection.sync_token = response["next_batch"]

        if self.nick and await self.connection.get_display_name(self.mxid) != self.nick:
            # This call is broken through the async wrapper so let's do it
            # ourselves.
            # await self.connection.set_display_name(self.mxid, self.nick)

            await self.connection._send("PUT", "/profile/{}/displayname".format(self.mxid),
                                        {"displayname": self.nick})

    async def listen(self, opsdroid):
        # Listen for new messages from the chat service
        while True:
            response = await self.connection.sync(
                self.connection.sync_token, timeout_ms=3000, filter=self.filter_id)
            self.connection.sync_token = response["next_batch"]
            try:
                room = response['rooms']['join'].get(self.room_id, None)
                if room and 'timeline' in room:
                    for event in room['timeline']['events']:
                        if event['content']['msgtype'] == 'm.text':
                            if event['sender'] != self.mxid:
                                message = Message(event['content']['body'],
                                                  event['sender'], None, self)
                                await opsdroid.parse(message)
            except Exception as e:
                _LOGGER.exception('Matrix Sync Error')

    async def respond(self, message):
        # Send message.text back to the chat service
        await self.connection.send_message(self.room_id, message.text)
