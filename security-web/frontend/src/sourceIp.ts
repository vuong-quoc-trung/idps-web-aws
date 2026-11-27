export function sourceIpLabel(a: {
  source: string;
  src_ip: string | null;
  client_ip?: string | null;
  network_src_ip?: string | null;
  client_ip_verified?: boolean | null;
  suricata_post_proxy?: boolean | null;
}): string {
  if (a.source !== "SURICATA") return a.src_ip ?? "—";
  if (a.client_ip_verified && a.client_ip)
    return `${a.client_ip} (Đã xác minh)`;
  if (a.network_src_ip && !/^(127\.|::1$)/.test(a.network_src_ip))
    return `${a.network_src_ip} (IP mạng)`;
  if (a.suricata_post_proxy) return "Chưa xác minh";
  return a.src_ip ? `${a.src_ip} (IP mạng / lịch sử)` : "Chưa xác minh";
}
