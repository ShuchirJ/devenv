# devenv
Simple disposable development environments ready within seconds.

### Images
Development environments can be based on one of the following images at the moment:
- [python:3.9-slim](https://hub.docker.com/_/python) (versions available: 3.9-3.13)
- [debian:bookworm-slim](https://hub.docker.com/_/debian)

### Features
- Pre-install pip packages
- Import files from directory
- SSH access
- Tailscale
- OpenVSCode

### Optional pre-installable apt packages
- git
- curl
- wget
- nano

### Databases to include
- MongoDB

### Usage
```bash
pip install devenv-cli
devenv --help
```

[Demo](demo.mp4)

### Supports:
- creating an environment
- Listing environments + ID/ports for each env
- Destroying an environment