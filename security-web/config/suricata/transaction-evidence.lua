local http=require("suricata.http")
local flow=require("suricata.flow")
local config=require("suricata.config")
function init(args) return {protocol="http"} end
function setup(args)
 generation=os.getenv("WS_SENSOR_GENERATION")
 if not generation then
  -- Legacy capture has no EVE generation binding: Rust keeps it Pending.
  local random=assert(io.open("/proc/sys/kernel/random/uuid","r"))
  generation=assert(random:read("*l")):gsub("-", ""); random:close()
 end
 assert(#generation==32 and not generation:find("[^a-f0-9]"))
 local marker=assert(io.open(config.log_path().."/proof-generation","w"))
 marker:write(generation);marker:close()
 file=assert(io.open(config.log_path().."/chain.tsv","a"))
end
function safe(v) if not v or #v>4096 or string.find(v,"[%c]") then return "" end return v end
function log(args)
 local tx=http.get_tx()
 if not args.tx_id or args.tx_id>9007199254740991 then return end
 local fields={tostring(flow.get():id()),string.format("%.0f",args.tx_id),
 safe(tx:request_header("X-WS-Proof")),safe(tx:response_header("X-WS-Receipt")),
 safe(tx:request_header("X-Forwarded-For")),safe(tx:request_header("X-Request-Id")),
 safe(tx:request_header("X-Forwarded-Proto")),safe(tx:request_header("Host")),generation}
 file:write(table.concat(fields,"\t").."\n");file:flush()
end
function deinit(args) file:close() end
