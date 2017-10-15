import time
import aiohttp
import logging
from opsdroid.connector import Connector
from opsdroid.message import Message

from matrix_client.async_api import AsyncHTTPAPI
from matrix_client.room import Room
from matrix_client.errors import MatrixRequestError, MatrixUnexpectedResponse
from matrix_client.client import MatrixClient

_LOGGER = logging.getLogger(__name__)


# def sync_api(api, timeout_ms=30000):
#     # TODO: Deal with presence
#     # TODO: Deal with left rooms
#     response = api.sync(api.sync_token, timeout_ms)#, filter=self.sync_filter)
#     api.sync_token = response["next_batch"]

    # for room_id, invite_room in response['rooms']['invite'].items():
    #     for listener in self.invite_listeners:
    #         listener(room_id, invite_room['invite_state'])

    # for room_id, left_room in response['rooms']['leave'].items():
    #     for listener in self.left_listeners:
    #         listener(room_id, left_room)
    #     if room_id in self.rooms:
    #         del self.rooms[room_id]

    # for room_id, sync_room in response['rooms']['join'].items():
    #     if room_id not in self.rooms:
    #         self._mkroom(room_id)
    #     room = self.rooms[room_id]
    #     room.prev_batch = sync_room["timeline"]["prev_batch"]

    #     for event in sync_room["state"]["events"]:
    #         event['room_id'] = room_id
    #         self._process_state_event(event, room)

    #     for event in sync_room["timeline"]["events"]:
    #         event['room_id'] = room_id
    #         room._put_event(event)

    #         # Dispatch for client (global) listeners
    #         for listener in self.listeners:
    #             if (
    #                 listener['event_type'] is None or
    #                 listener['event_type'] == event['type']
    #             ):
    #                 listener['callback'](event)

    #     for event in sync_room['ephemeral']['events']:
    #         event['room_id'] = room_id
    #         room._put_ephemeral_event(event)

    #         for listener in self.ephemeral_listeners:
    #             if (
    #                 listener['event_type'] is None or
    #                 listener['event_type'] == event['type']
    #             ):
    #                 listener['callback'](event)


class ConnectorMatrix(Connector):
    def __init__(self, config):
        # Init the config for the connector
        self.name = "ConnectorMatrix"  # The name of your connector
        self.config = config  # The config dictionary to be accessed later
        self.default_room = "#DnD:matrix.org"  # The default room for messages

    async def connect(self, opsdroid):
        # Create connection object with chat library
        # _LOGGER.debug("Connecting to matrix")
        # client = MatrixClient("https://matrix.org")
        # token = client.login_with_password(username="@DMBot:matrix.org",
        #                                    password="dungeonmaster2017")
        # room = client.join_room("#DnD:matrix.org")
        async with aiohttp.ClientSession() as session:
            mapi = AsyncHTTPAPI("http://matrix.org", session)
            self.session = session
            login_response = await mapi.login("m.login.password", user="@DMBot:matrix.org", password="dungeonmaster2017")
            mapi.token = login_response['access_token']
            mapi.sync_token = None
            response = await mapi.join_room(self.default_room)
            self.room_id = response['room_id']
        self.connection = mapi

    async def listen(self, opsdroid):
        # Listen for new messages from the chat service
        while True:
            response = await self.connection.sync(self.connection.sync_token, 3000, filter='{ "room": { "timeline" : { "limit" : %i } } }' % 10)
            self.connection.sync_token = response["next_batch"]
            _LOGGER.debug("listening")

    async def respond(self, message):
        # Send message.text back to the chat service
        _LOGGER.debug("response triggered")
        self.connection.send_message(self.room_id, message)
