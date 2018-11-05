# opsdroid connector Matrix

A connector for [opsdroid](https://github.com/opsdroid/opsdroid) to receive and respond to messages in [Matrix](https://matrix.org/) rooms. 

Maintained by [@SolarDrew](https://github.com/SolarDrew).

## Requirements

To use this connector you will need to have a Matrix account, and login using your Matrix username (mxid) and password.

## Configuration

```yaml
connectors:
  - name: matrix
    # Required
    mxid: "@username:matrix.org"
    password: "mypassword"
    # Name of a single room to connect to
    room: "#matrix:matrix.org"
    # Alternatively, a dictionary of multiple rooms
    # One of these should be named 'main'
    rooms:
      'main': 
        alias: '#matrix:matrix.org'
      'other': 
        alias: '#riot:matrix.org'
        send_m_notice: False  # Send messages to this room as m.notice events rather than m.message
    # Optional
    homeserver: "https://matrix.org"
    nick: "Botty McBotface"  # The nick will be set on startup
    room_specific_nicks: False  # Look up room specific nicknames of senders (expensive in large rooms)
    send_m_notice: False  # Send all messages as m.notice events rather than m.message
```
