# Decoder for the Linux `struct tcp_info` returned by getsockopt(IPPROTO_TCP, TCP_INFO).
#
# Layout source: include/uapi/linux/tcp.h. The struct only ever grows by appending fields,
# so the table below describes a known 248-byte prefix: an older kernel returns a shorter
# buffer and its missing trailing fields decode as None instead of raising, while a newer
# kernel returns a longer buffer whose unknown tail is ignored. RunMetadata.tcp_info_bytes
# records how many bytes the kernel actually wrote, so a reader can tell which columns were
# available. The host kernel for these measurements (6.18.54.1-microsoft-standard-WSL2)
# returns 280 bytes -- 32 bytes of fields newer than this table, which are not decoded.
#
# On x86-64 every field below already sits at its natural alignment, so the struct has no
# interior padding and a packed ("=") decode reproduces the kernel layout exactly.
#
# Verified on the host kernel by decoding a live socket and comparing every field against
# `ss -ti` for the same socket (rtt/rttvar, mss, pmtu, cwnd, ssthresh, bytes_acked,
# bytes_sent, segs_out, data_segs_out, delivered, min_rtt, busy_time, retrans/total_retrans,
# rcv_space, rcv_ssthresh and snd_wnd all matched).

import socket
import struct

# (name, struct format code, unit), in kernel declaration order.
TCP_INFO_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("state", "B", "enum"),
    ("ca_state", "B", "enum"),
    ("retransmits", "B", "count"),
    ("probes", "B", "count"),
    ("backoff", "B", "count"),
    ("options", "B", "flags"),
    ("wscale", "B", "flags"),  # snd_wscale:4, rcv_wscale:4
    ("app_limited", "B", "flags"),  # delivery_rate_app_limited:1, fastopen_client_fail:2
    ("rto", "I", "us"),
    ("ato", "I", "us"),
    ("snd_mss", "I", "bytes"),
    ("rcv_mss", "I", "bytes"),
    ("unacked", "I", "segments"),
    ("sacked", "I", "segments"),
    ("lost", "I", "segments"),
    ("retrans", "I", "segments"),
    ("fackets", "I", "segments"),
    ("last_data_sent", "I", "ms"),
    ("last_ack_sent", "I", "ms"),
    ("last_data_recv", "I", "ms"),
    ("last_ack_recv", "I", "ms"),
    ("pmtu", "I", "bytes"),
    ("rcv_ssthresh", "I", "bytes"),
    ("rtt", "I", "us"),
    ("rttvar", "I", "us"),
    ("snd_ssthresh", "I", "segments"),
    ("snd_cwnd", "I", "segments"),
    ("advmss", "I", "bytes"),
    ("reordering", "I", "segments"),
    ("rcv_rtt", "I", "us"),
    ("rcv_space", "I", "bytes"),
    ("total_retrans", "I", "segments"),
    ("pacing_rate", "Q", "bytes/s"),
    ("max_pacing_rate", "Q", "bytes/s"),
    ("bytes_acked", "Q", "bytes"),
    ("bytes_received", "Q", "bytes"),
    ("segs_out", "I", "segments"),
    ("segs_in", "I", "segments"),
    ("notsent_bytes", "I", "bytes"),
    ("min_rtt", "I", "us"),
    ("data_segs_in", "I", "segments"),
    ("data_segs_out", "I", "segments"),
    ("delivery_rate", "Q", "bytes/s"),
    ("busy_time", "Q", "us"),
    ("rwnd_limited", "Q", "us"),
    ("sndbuf_limited", "Q", "us"),
    ("delivered", "I", "segments"),
    ("delivered_ce", "I", "segments"),
    ("bytes_sent", "Q", "bytes"),
    ("bytes_retrans", "Q", "bytes"),
    ("dsack_dups", "I", "count"),
    ("reord_seen", "I", "count"),
    ("rcv_ooopack", "I", "count"),
    ("snd_wnd", "I", "bytes"),
    ("rcv_wnd", "I", "bytes"),
    ("rehash", "I", "count"),
    ("total_rto", "H", "count"),
    ("total_rto_recoveries", "H", "count"),
    ("total_rto_time", "I", "ms"),
)

TCP_INFO_UNITS = {name: unit for name, _, unit in TCP_INFO_FIELDS}
TCP_INFO_FORMAT = "=" + "".join(fmt for _, fmt, _ in TCP_INFO_FIELDS)
STRUCT_SIZE = struct.calcsize(TCP_INFO_FORMAT)
assert STRUCT_SIZE == 248, f"unexpected tcp_info size: {STRUCT_SIZE}"

# Ask for more than the struct we know about so a newer kernel never silently truncates.
REQUEST_SIZE = 2 * STRUCT_SIZE

TCP_CONGESTION_NAME_SIZE = 16

type TcpInfo = dict[str, int | None]


def parse_tcp_info(data: bytes) -> TcpInfo:
    info: TcpInfo = {}
    offset = 0

    for name, fmt, _ in TCP_INFO_FIELDS:
        end = offset + struct.calcsize("=" + fmt)
        # A field past the end of the returned buffer is absent on this (older) kernel.
        info[name] = struct.unpack_from("=" + fmt, data, offset)[0] if end <= len(data) else None
        offset = end

    return info


def get_tcp_info_bytes(sock: socket.socket) -> bytes:
    return sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_INFO, REQUEST_SIZE)


def get_tcp_info(sock: socket.socket) -> TcpInfo:
    return parse_tcp_info(get_tcp_info_bytes(sock))


def get_tcp_algorithm(sock: socket.socket) -> str:
    name = sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_CONGESTION, TCP_CONGESTION_NAME_SIZE)
    return name.split(b"\x00", 1)[0].decode("ascii")


def field_delta(curr: TcpInfo, prev: TcpInfo, name: str) -> int | None:
    after, before = curr[name], prev[name]
    return None if after is None or before is None else after - before
