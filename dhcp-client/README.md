# dhcp-client — Build Your Own DHCP Client

Coding Challenge #94, worked in `somecoolprojects/`.
Docs first, then code — see `docs/`.

A Python 3 standard-library-only DHCP client (RFC 2131): it builds
and parses DHCPDISCOVER / DHCPOFFER / DHCPREQUEST / DHCPACK /
DHCPNAK / DHCPDECLINE / DHCPRELEASE packets and runs the DORA
handshake (Discover → Offer → Request → Acknowledge) against a
DHCP server, returning the lease (IP, subnet mask, routers, DNS
servers, lease time, server id).

## Usage

Against a server on loopback (e.g. for testing with a fake server):

```sh
python3 dhcp_client.py --mac aa:bb:cc:dd:ee:ff \
    --server 127.0.0.1 --server-port 6767 --timeout 5
```

Output on success:

```
ip: 192.168.1.100
subnet_mask: 255.255.255.0
routers: 192.168.1.1
dns_servers: 8.8.8.8
lease_time: 3600
server_id: 192.168.1.1
```

Other modes:

```sh
# Send DHCPRELEASE after obtaining the lease
python3 dhcp_client.py --mac aa:bb:cc:dd:ee:ff --server 127.0.0.1 \
    --server-port 6767 --release-after
# Discover and decline the offer instead of requesting it
python3 dhcp_client.py --mac aa:bb:cc:dd:ee:ff --server 127.0.0.1 \
    --server-port 6767 --decline
```

## Live use — read this first

Live use needs broadcast privileges and, for the standard client
port 68, usually root:

```sh
sudo python3 dhcp_client.py --mac <your-mac> --broadcast \
    --client-port 68 --server-port 67
```

`--broadcast` sends to 255.255.255.255 instead of `--server`.
This program **never changes the host's network configuration**:
on ACK it prints the lease; applying it to a NIC (e.g. with `ip
addr add`) is left to the operator, deliberately. Do not run the
broadcast form against a network you do not administer — a rogue
DISCOVER can disturb a real DHCP server's lease pool.

## Run tests

```sh
python3 -m unittest discover -s tests -v
```

All network tests use a fake DHCP server on 127.0.0.1 with an
ephemeral port. No test broadcasts, contacts a real DHCP server, or
changes host configuration.

## Files

- `dhcp_client.py` — packet encode/decode, builders, `Lease`,
  `DhcpClient`, CLI.
- `docs/SPEC.md` — challenge spec, including the fyi-slug 404 caveat.
- `docs/DESIGN.md` — assumptions, data model, divergences.
- `docs/TEST_PLAN.md` — test cases.
- `tests/test_dhcp_client.py` — the test suite (incl. fake server).
