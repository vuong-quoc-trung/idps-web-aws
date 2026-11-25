CREATE FUNCTION ws_notify_alert_created() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- Preserve headroom in PostgreSQL's shared notification queue.
    IF pg_notification_queue_usage() < 0.5 THEN
        PERFORM pg_notify('ws_alert_created', NEW.id::text);
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'alert notification unavailable';
    RETURN NEW;
END
$$;
CREATE TRIGGER ws_alert_created AFTER INSERT ON security_alerts
FOR EACH ROW EXECUTE FUNCTION ws_notify_alert_created();
