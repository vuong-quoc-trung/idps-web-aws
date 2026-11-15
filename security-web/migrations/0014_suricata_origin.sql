-- Additive: old events keep their observed src_ip; no guessed historical attribution.
ALTER TABLE security_alerts
  ADD COLUMN client_ip inet,
  ADD COLUMN network_src_ip inet,
  ADD COLUMN client_ip_verified boolean,
  ADD COLUMN suricata_post_proxy boolean,
  ADD CONSTRAINT verified_suricata_client CHECK (
    client_ip_verified IS DISTINCT FROM TRUE OR
    (source='SURICATA' AND client_ip IS NOT NULL AND network_src_ip IS NOT NULL AND suricata_post_proxy IS TRUE));
CREATE INDEX security_alerts_network_source_idx ON security_alerts(network_src_ip) WHERE network_src_ip IS NOT NULL;
