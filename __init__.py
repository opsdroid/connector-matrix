import sys
import aiohttp
import logging
from opsdroid.connector import Connector
from opsdroid.message import Message

from matrix_client.async_api import AsyncHTTPAPI

_LOGGER = logging.getLogger(__name__)


class ConnectorMatrix(Connector):
    def __init__(self, config):
        # Init the config for the connector
        self.name = "ConnectorMatrix"  # The name of your connector
        self.config = config  # The config dictionary to be accessed later
        self.default_room = "#tan:matrix.org"  # The default room for messages
        self.botname = "@DMBot:matrix.org"

    async def connect(self, opsdroid):
        # Create connection object with chat library
        session = aiohttp.ClientSession()
        mapi = AsyncHTTPAPI("http://matrix.org", session)
        self.session = session
        login_response = await mapi.login("m.login.password",
                                          user=self.botname,
                                          password="somepassword")
        mapi.token = login_response['access_token']
        mapi.sync_token = None
        response = await mapi.join_room(self.default_room)
        self.room_id = response['room_id']
        self.connection = mapi

    async def listen(self, opsdroid):
        # Listen for new messages from the chat service
        while True:
            try:
                response = await self.connection.sync(
                    self.connection.sync_token, 3000,
                    filter='{ "room": { "timeline" : { "limit" : 10 } } }')
                self.connection.sync_token = response["next_batch"]
                try:
                    room = response['rooms']['join'][self.room_id]
                except KeyError:
                    continue
                for event in room['timeline']['events']:
                    if event['content']['msgtype'] == 'm.text':
                        if event['sender'] != self.botname:
                            message = Message(event['content']['body'],
                                              event['sender'],
                                              None,
                                              self)
                            await opsdroid.parse(message)
            except KeyError:
                continue
            except Exception as e:
                _LOGGER.debug('request failed', e)
                sys.exit()

    async def respond(self, message):
        # Send message.text back to the chat service
        await self.connection.send_message(self.room_id, message.text)
