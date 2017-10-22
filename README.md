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
    repo: https://github.com/solardrew/connector-matrix.git
    mxid: "@username:matrix.org"
    password: "mypassword"
    room: "#matrix:matrix.org"
    # Optional
    homeserver: "https://matrix.org"
    nick: "Botty McBotface"  # The nick will be set on startup
```

## License

GNU General Public License Version 3 (GPLv3)
