-- Metadata links only; existing alert rows and enforcement decisions are unchanged.
CREATE TABLE detector_alert_links (
 alert_id BIGINT PRIMARY KEY REFERENCES security_alerts(id) ON DELETE CASCADE,
 request_id TEXT,
 source_instance TEXT NOT NULL,
 flow_id TEXT,
 tx_id BIGINT,
 link_basis TEXT NOT NULL CHECK(link_basis IN ('REQUEST_ID','SENSOR_TRANSACTION','FLOW_CONTEXT','UNLINKED'))
);
CREATE INDEX detector_links_request ON detector_alert_links(request_id) WHERE request_id IS NOT NULL;
CREATE INDEX detector_links_tx ON detector_alert_links(source_instance,flow_id,tx_id);
