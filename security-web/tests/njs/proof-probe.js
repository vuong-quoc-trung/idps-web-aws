// Capability test only: GET metadata, no production trust integration.
import nodecrypto from 'crypto';
function randomBytes(n) { return Buffer.from(crypto.getRandomValues(new Uint8Array(n))); }
import fs from 'fs';
function material(r) {
    const path = r.variables.probe_key_file;
    const st = fs.statSync(path);
    const gid = r.variables.probe_key_gid || '';
    if (gid !== '') {
        // Opt-in dedicated-group layout. Group membership is a deployment trust boundary.
        if (!/^[1-9][0-9]*$/.test(gid) || st.uid !== 0 || st.gid !== Number(gid) ||
            (st.mode & 0o777) !== 0o640 || !st.isFile()) throw Error('unsafe managed key');
        const parent = fs.statSync(path.substring(0, path.lastIndexOf('/')));
        if (parent.uid !== 0 || parent.gid !== Number(gid) ||
            (parent.mode & 0o777) !== 0o750 || !parent.isDirectory()) throw Error('unsafe managed directory');
        if (fs.lstatSync(path).isSymbolicLink()) throw Error('symlink key');
    } else if ((st.mode & 0o077) !== 0) throw Error('unsafe key permissions');
    return JSON.parse(fs.readFileSync(path, 'utf8'));
}
function mac(key, value) { return nodecrypto.createHmac('sha256', Buffer.from(key, 'hex')).update(value).digest('hex'); }
// Comparison blinding: fresh random HMAC key for each comparison. This avoids
// comparing the stable secret MAC with a variable-time string comparison.
function equal(a, b) {
    const blind = randomBytes(32);
    return nodecrypto.createHmac('sha256', blind).update(a).digest('hex') ===
           nodecrypto.createHmac('sha256', blind).update(b).digest('hex');
}
function digest(s) { return nodecrypto.createHash('sha256').update(s).digest('hex'); }
function wire(key, domain, fields) {
    const body = Buffer.from(JSON.stringify(fields)).toString('base64url');
    return body + '.' + mac(key, domain + body);
}
function sign(r) {
    const k = material(r), now = Date.now();
    return wire(k.key, 'ws-request-v1:', [1, k.kid, k.epoch, randomBytes(16).toString('hex'),
        r.remoteAddress, r.variables.request_id, r.method, r.variables.scheme,
        r.variables.http_host, digest(r.variables.request_uri), now, now + 60000]);
}
function verify(r) {
    try {
        const proof = r.headersIn['X-WS-Proof'] || '';
        if (proof.length > 4096 || r.rawHeadersIn.filter(h => h[0].toLowerCase() === 'x-ws-proof').length !== 1) return 'invalid';
        const parts = proof.split('.');
        if (parts.length !== 2 || !/^[a-f0-9]{64}$/.test(parts[1]) || !/^[A-Za-z0-9_-]+$/.test(parts[0])) return 'invalid';
        const k = material(r);
        if (!equal(parts[1], mac(k.key, 'ws-request-v1:' + parts[0]))) return 'invalid';
        const p = JSON.parse(Buffer.from(parts[0], 'base64url').toString());
        if (Buffer.from(JSON.stringify(p)).toString('base64url') !== parts[0]) return 'invalid';
        const now = Date.now();
        if (p.length !== 12 || !/^[A-Za-z0-9-]{1,64}$/.test(p[1]) || !/^[a-f0-9]{32}$/.test(p[2]) || !/^[A-Z-]{1,32}$/.test(p[6]) || typeof p[8] !== 'string' || p[8].length > 255 || !/^[!-~]+$/.test(p[8]) || /["\\]/.test(p[8]) || p[0] !== 1 || p[1] !== k.kid || p[2] !== k.epoch ||
            !/^[a-f0-9]{32}$/.test(p[3]) || !/^[a-f0-9]{32}$/.test(p[5]) ||
            !Number.isSafeInteger(p[10]) || !Number.isSafeInteger(p[11]) || p[11]-p[10] !== 60000 ||
            p[10] > now + 1000 || p[11] < now || p[6] !== r.method ||
            p[9] !== digest(r.variables.request_uri) || p[8] !== r.variables.http_host ||
            p[4] !== r.headersIn['X-Forwarded-For'] || p[4] !== r.headersIn['X-Real-IP'] ||
            p[5] !== r.headersIn['X-Request-Id'] || p[7] !== r.headersIn['X-Forwarded-Proto'] ||
            !['http','https'].includes(p[7])) return 'invalid';
        if (!ngx.shared.nonces.add(p[2] + ':' + p[3], '1', 65000)) return 'replay';
        r.variables.probe_receipt = wire(k.key, 'ws-receipt-v1:', [1,k.kid,k.epoch,p[3],digest(proof),'accepted',now]);
        return 'ok';
    } catch (_) { return 'invalid'; }
}
export default {sign, verify};
