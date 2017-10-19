# opsdroid connector Matrix

A connector for [opsdroid](https://github.com/opsdroid/opsdroid) to receive and respond to messages in matrix rooms.

## Requirements

To use this connector you will need to have a matrix account, and login using your matrix username (mxid) and password.

## Configuration

```yaml
connectors:
  - name: matrix
    repo: https://github.com/solardrew/connector-matrix.git
    mxid: "@username:matrix.org"
    password: "mypassword"
    homeserver: "https://matrix.org"
    nick: "Botty McBotface"
    room: "#matrix:matrix.org"
```

The homeserver and nick options are optional. The provided nick will be set on startup.

## License

GNU General Public License Version 3 (GPLv3)
