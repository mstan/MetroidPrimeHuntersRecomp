# Metroid Prime Hunters — Wi-Fi game-layer protocol

Reverse-engineered 2026-08-19 from our own USA ROM (AMHE) and our own
captured wire traffic, to diagnose the friend-match in-room stall
(beads-lqa.6). All facts here are re-derived independently; the DWC/GameSpy
semantics below are cross-checked against public research only, never copied
from any leaked SDK source.

Addresses are ARM9 main-RAM addresses observed in a live online session
(`scratch/wifi-stability/fable-ram-capture/mainram.bin`, base `0x02000000`).
The netcode lives in **ARM9 overlay 4** (the "Multiplayer: WFC" overlay per
the MphRead / hackyourlife overlay maps), so these addresses are only valid
while that overlay is resident.

## Stack

```
game message set   <- this document
  DWC transport    "DT" magic, 8-byte header, reliable/unreliable, per-AID
  GT2              0xFEFE framing, SYN/ESN reliability  (GameSpy)
  QR2 / SB / GPCM  matchmaking + master server           (GameSpy, TCP/UDP)
  slirp            host NAT / virtual LAN 10.64.<inst>.16
```

The DWC layer strips its own `"DT"` framing before calling the game's
receive callback, so everything below is the raw game payload.

MPH sends its gameplay messages as DWC **unreliable** user data, so on the
UDP flow between the two consoles they appear raw — no `fe fe`, no `DT`.
Reliable DWC sends (and the match handshake) do carry `"DT"`, which is why
the framing differs between the join sequence and the match itself.

Everything before the match — the GPCM buddy-message `MAT` commands (a raw
command byte immediately after `"GPCM3vMAT"`), the `SBCM` server-browser
relay that hands over the local address, the direct GT2 connect on the
private addresses when both consoles share one public IP, and the DT-framed
match SYN / SYN_ACK / ACK — completes healthily and is out of scope here.

## Message framing

Each game datagram carries a **set** of typed sub-messages:

```
u32  type_bitmask        ; which of 32 message types are present
for each set bit t (ascending):
    u8[size_table[t]]    ; fixed-size body, except type 14 (2-byte length prefix)
if (type_bitmask & 0x80000000):
    u32  ack_bitmask     ; which types this packet acknowledges
    for each set bit in ack_bitmask: u8 counter  ; echo of sender's per-type counter
```

Bit 31 is the ack-carrier flag, not a message type. 26 of 32 type slots are
allocated.

### Size table (`0x02194e80`, u16 per type)

```
t :  0  1  2  3   4   5  6   7  8  9 10 11 12 13  14 15 16 17   18 19 20 21 22 23 24 25 26 27 28 29 30 31
sz:  3  9  3 22 117 21  6 131  5 15 15  1 25  2 512  2  5 12  155  5 17 12 12 12 12 11  3 15  4 16 30  1
```

Type 14 is variable: the stored size 512 is a cap; the body is a 2-byte
length followed by that many bytes (see RX parser special-case `t==0xe`).

## Key routines (RAM addresses)

| addr | role |
|---|---|
| `FUN_0214daac` | **RX parser.** Reads `type_bitmask`, dispatches each present type through the handler table at `0x02194f3c`, stamps `last_recv[sender]` (`0x02198f74`, per-AID u64 tick). |
| `FUN_0214fa28` | **TX flush.** Walks the 4 AIDs, builds one datagram per peer from the pending-type mask (`0x0219964c`), appends ack section when bit31 set, hands to `FUN_02152940 → DWC send`. Gated on the connected mask `0x02198cec`, skips own AID `0x020d9cb8`. |
| `FUN_021515d8` | **Ack queuer.** Every RX handler calls it; sets bit31 in the peer's pending mask and stores the echoed counter. The steady "5-byte `00 08 00 00 NN` / 9-byte" traffic is type-11 (size 1) pings plus these acks — normal keepalive, not a fault. |
| `FUN_02151134` | Per-frame pump: runs 26 `FUN_02151350` passes, one per type queue. |
| `FUN_02151030` | **Room activation** — sets `netstate` (`0x02198cd8`) to 1. |
| `FUN_0214f130` | **Type-6 builder** (hunter/slot sync). Gated on `netstate == 1`. Body: `u8 slot_index`, `u8 (slot & 0x7f) | (flag<<7)`, `u32`. `slot = 0x7f` means "no hunter picked". |
| `FUN_0214dde8` | **Guest room watchdog** — the "HOST HAS ABANDONED THIS GAME" path. Arms on `last_recv[server_aid]` staleness once the guest is in-room. |
| `FUN_0214ca08` | Netcode reset (clears AID table, per-slot state). |

### Netcode globals

| addr | meaning |
|---|---|
| `0x020eaaf0` | mode flags; bit5 (`0x20`) = "in a live Wi-Fi session" — most senders gate on it |
| `0x020d9cb8` | own AID |
| `0x02198cc4` | server (host) AID |
| `0x02198cec` | connected-peer bitmask |
| `0x02198cd8` | netstate (1 = room active, 2 = joined/pre-active) |
| `0x02194e60` | local hunter slot (`0xff` = unset) |
| `0x02198f74` | per-AID last-receive tick (u64 ×4) |

## The friend-match stall (beads-lqa.6)

Captured post-join state (both instances, `scratch/wifi-stability/
fable-friendmatch-run3/instanceN/mainram-postjoin.bin`):

- Host: `netstate=1`, `conn_mask=0x1`, `own_aid=0`, players=1.
- Guest: `netstate=2`, `conn_mask=0x3`, `own_aid=1`, `server_aid=0`, players=2.

Both AIDs are assigned, DWC is fully linked, and bidirectional game traffic
flows the entire time. The guest is **in the room, on SELECT HUNTER**. It
stays at `netstate=2` (not yet room-active for its own sends) until its
hunter is picked; the host slot-polls it (type-6, `slot=0x7f`) for a few
seconds and then idles. If the guest never picks a hunter, the host's
~195-second room/link timer expires, it tears down the GT2 link, and the
guest's watchdog (`FUN_0214dde8`) fires "HOST HAS ABANDONED".

**This is a timing problem, not a protocol fault.** A human picks a hunter
in seconds; the automation driver idled the guest on SELECT HUNTER for
minutes. The fix is on the driver side (pick promptly after join) — tracked
as the acceptance-pacing work on beads-lqa.6 / beads-lqa.1.

## Reproducing the analysis

```
# capture RAM in the online state
py -3 <scratch>/capture_ram.py                       # -> mainram.bin
# import + analyze headlessly
analyzeHeadless <repo>/ghidra MPH -import mainram.bin \
    -processor ARM:LE:32:v5t -loader BinaryLoader -loader-baseAddr 0x02000000
# post-join dumps come straight from the driver
run_mph_friend_match.py ... --dump-ram              # -> mainram-postjoin.bin
```

Ghidra project: `ghidra/MPH` (databases git-ignored; commit only
`ghidra/annotations/*.json` once symbols are named).
