# BIG-IP Logging Notes

Pools, Log Destinations, and Log Publishers will be used for: AFM, DoS, BOT, and iRule HSL logging.  AdvWAF/ASM logging uses a slightly different mechanism.
 
### General Steps:
* Create pool(s) for new syslog servers(s).
* Create unformatted HSL destination(s) pointing to pool(s) with syslog server(s).
* Create formatted HSL destination(s) pointing to unformatted HSL destination(s).
* Create publisher(s) containing multiple or one specific desired destination(s).
* Update or Create new Security Logging Profiles to point to the new logging publisher(s).
* Apply Security Logging Profiles to any/all virtual servers.
* Additionally, for AFM/DOS be sure to configure the device log publisher for AFM Management & Device DoS:
  * Options => Firewall Options => Log Publisher.
  * Dos Protection => Device Protection => Log Publisher

### Note differences between how ASM/AdvWAF logging works and other security features: 
You can only have one security logging profile on a VIP with a specific configuration for: AFM, Bot, or DoS.  So if you want to send those logs to multiple destinations you need to send it to a publisher that contains all the desired destinations.

However, for ASM/AdvWAF, because it doesn't use the log publisher infrastructure, you can have multiple security logging profiles applied to a single VIP with ASM/AdvWAF configured.  This is useful when you want to send AdvWAF/ASM logs to multiple destinations.
 
I advise you create a single security logging profile for: AFM/DoS/BoT, however you'll need individual security logging profiles for each destination with AdvWAF/ASM config.

* Summary:
  * ASM: Separate Security Logging profiles for each different destinations.
  * AFM/DoS/BOT/Etc: Single security logging profile pointing to a log publisher with all the desired destinations.

### Supporting Docs:

* High Speed Logging for AFM:
  * https://techdocs.f5.com/en-us/bigip-15-0-0/external-monitoring-of-big-ip-systems-implementations/configuring-remote-high-speed-logging-of-network-firewall-events.html
 
* High Speed Logging for DoS:
    * https://techdocs.f5.com/en-us/bigip-15-1-0/big-ip-system-dos-protection-and-protocol-firewall-implementations/configuring-high-speed-remote-logging-of-protocol-security-events.html
 
* High Speed Logging for ASM/AdvWAF: 
    * https://techdocs.f5.com/en-us/bigip-14-1-0/big-ip-asm-implementations-14-1-0/logging-application-security-events.html
 
* Non High Speed, standard Syslog for all of BIG-IP's linux management station's syslog-ng events:
    * https://my.f5.com/manage/s/article/K13080
 

### Ancillary docs:
* High Speed Logging distribution method:
  * https://my.f5.com/manage/s/article/K17398
* Syslog Formated Facility/Severity options, can be configured in the log destination:
  * https://clouddocs.f5.com/cli/tmsh-reference/v13/modules/sys/sys_log-config_destination_remote-syslog.html
* F5 BIG-IP System/Management syslog Logging Facilities:
  * https://my.f5.com/manage/s/article/K13317




## Example HSL Config:
This config sends to separate syslogs listeners for each different module/log source on the BIG-IP.
Note: the examples use 192.0.2.100 as the remote syslog server's IP.

### Log Destinations
```
create ltm pool hsl-dest-afm   { members replace-all-with { 192.0.2.100:2514 } monitor tcp }
create ltm pool hsl-dest-dos   { members replace-all-with { 192.0.2.100:3514 } monitor tcp }
create ltm pool hsl-dest-bot   { members replace-all-with { 192.0.2.100:4514 } monitor tcp }
create ltm pool hsl-dest-ipsec { members replace-all-with { 192.0.2.100:5514 } monitor tcp }

create sys log-config destination remote-high-speed-log hsl-dest-raw-afm   { pool-name /Common/hsl-dest-afm distribution adaptive protocol tcp }
create sys log-config destination remote-high-speed-log hsl-dest-raw-dos   { pool-name /Common/hsl-dest-dos distribution adaptive protocol tcp }
create sys log-config destination remote-high-speed-log hsl-dest-raw-bot   { pool-name /Common/hsl-dest-bot distribution adaptive protocol tcp }
create sys log-config destination remote-high-speed-log hsl-dest-raw-ipsec { pool-name /Common/hsl-dest-ipsec distribution adaptive protocol tcp }

create sys log-config destination splunk remotedest-splunk-afm   { forward-to /Common/hsl-dest-raw-afm }
create sys log-config destination splunk remotedest-splunk-dos   { forward-to /Common/hsl-dest-raw-dos }
create sys log-config destination splunk remotedest-splunk-bot   { forward-to /Common/hsl-dest-raw-bot }
create sys log-config destination splunk remotedest-splunk-ipsec { forward-to /Common/hsl-dest-raw-ipsec }
```

### Log Publishers
Note: these commands create remote publishers without telemetry streaming destinations if you want to only send to HSL & some locally.
However, the modify commands add Telemetry Streaming destination, if you wan to send log messages to both HSL & TS.
```
create sys log-config publisher publisher-afm   { destinations replace-all-with { /Common/remotedest-splunk-afm   /Common/local-db-publisher } }
create sys log-config publisher publisher-dos   { destinations replace-all-with { /Common/remotedest-splunk-dos   /Common/local-db-publisher } }
create sys log-config publisher publisher-dos-no-local   { destinations replace-all-with { /Common/remotedest-splunk-dos } }
create sys log-config publisher publisher-bot   { destinations replace-all-with { /Common/remotedest-splunk-bot   } }
create sys log-config publisher publisher-ipsec { destinations replace-all-with { /Common/remotedest-splunk-ipsec /Common/local-syslog { } } }

modify sys log-config publisher publisher-afm   { destinations replace-all-with { /Common/remotedest-splunk-afm   /Common/telemetry_formatted /Common/local-db } }
modify sys log-config publisher publisher-dos   { destinations replace-all-with { /Common/remotedest-splunk-dos   /Common/telemetry_formatted /Common/local-db } }
modify sys log-config publisher publisher-dos-no-local   { destinations replace-all-with { /Common/remotedest-splunk-dos   /Common/telemetry_formatted } }
modify sys log-config publisher publisher-bot   { destinations replace-all-with { /Common/remotedest-splunk-bot   /Common/telemetry_formatted } }
modify sys log-config publisher publisher-ipsec { destinations replace-all-with { /Common/remotedest-splunk-ipsec /Common/telemetry_formatted /Common/local-syslog { } } }
```

## Example Security Log Profiles:
This creates a single log profile for bot/dos/afm; and then separate profiles for asm that send to local/ts/hsl.

```
create security log profile /Common/default-remote-bot-dos-afm-log-profile { bot-defense replace-all-with { default-remote-bot-dos-afm-log-profile { filter { log-alarm enabled log-block enabled log-captcha enabled log-challenge-failure-request enabled log-honey-pot-page enabled log-rate-limit enabled log-redirect-to-pool enabled log-tcp-reset enabled } local-publisher /Common/local-db-publisher remote-publisher /Common/publisher-bot } } dos-application replace-all-with { default-remote-bot-dos-afm-log-profile { local-publisher local-db-publisher remote-publisher /Common/publisher-dos-no-local } } dos-network-publisher /Common/publisher-dos network replace-all-with { default-remote-bot-dos-afm-log-profile { filter { log-acl-match-accept enabled log-acl-match-drop enabled log-acl-match-reject enabled log-translation-fields enabled } publisher /Common/publisher-afm rate-limit { acl-match-accept 1500 acl-match-drop 500 acl-match-reject 500 aggregate-rate 1500 } } } protocol-dns-dos-publisher /Common/publisher-dos protocol-sip-dos-publisher /Common/publisher-dos traffic-statistics { active-flows enabled log-publisher /Common/publisher-afm missed-flows enabled reaped-flows enabled syncookies enabled syncookies-whitelist enabled } }

create security log profile /Common/default-remote-telemetry-asm-log-profile { application replace-all-with { default-remote-telemetry-asm-log-profile { filter replace-all-with { log-challenge-failure-requests { values replace-all-with { disabled } } request-type { values replace-all-with { illegal-including-staged-signatures } } } local-storage disabled logger-type remote remote-storage splunk servers replace-all-with{ 255.255.255.254:6514 { } } } } }
create security log profile /Common/default-remote-hsl-asm-log-profile { application replace-all-with { default-remote-telemetry-asm-log-profile { filter replace-all-with { log-challenge-failure-requests { values replace-all-with { disabled } } request-type { values replace-all-with { illegal-including-staged-signatures } } } local-storage disabled logger-type remote remote-storage splunk servers replace-all-with{ 192.0.2.100:1514 { } } } } }
create security log profile /Common/default-local-asm-log-profile { application replace-all-with { default-remote-telemetry-asm-log-profile { filter replace-all-with { log-challenge-failure-requests { values replace-all-with { disabled } } request-type { values replace-all-with { illegal-including-staged-signatures } } } local-storage enabled } } }
```

## Example modifying all VS's to add Security Log Profiles Profiles:
```
modify ltm virtual all security-log-profiles replace-all-with { /Common/default-remote-telemetry-asm-log-profile /Common/default-remote-hsl-asm-log-profile /Common/default-local-asm-log-profile  /Common/default-remote-bot-dos-afm-log-profile }
```

## Example modifying other services to use the new publishers:
modify net ipsec ike-daemon ikedaemon { log-publisher publisher-ipsec }
modify security dos device-config /Common/dos-device-config log-publisher /Common/publisher-dos
modify security firewall config-change-log { log-publisher /Common/publisher-afm }

## Example rsyslog Config:
This config has separate listeners for each different module/log source on the BIG-IP.

```
mhermsdorfer@herm-arm:~$ cat /etc/rsyslog.d/80-remotebigip.conf
module(load="imtcp")

template(name="TemplateRemoteBigIPMgmt"  type="string" string="/var/log/%hostname%/%programname%.log")
ruleset(name="remoteBigipMgmt"){  action(type="omfile" dynaFile="TemplateRemoteBigIPMgmt"  dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="514" ruleset="remoteBigipMgmt")

template(name="TemplateRemoteBigIPASM"   type="string" string="/var/log/%fromhost%/asm.log")
ruleset(name="remoteBigipASM"){   action(type="omfile" dynaFile="TemplateRemoteBigIPASM"   dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="1514" ruleset="remoteBigipASM")

template(name="TemplateRemoteBigIPAFM"   type="string" string="/var/log/%fromhost%/afm.log")
ruleset(name="remoteBigipAFM"){   action(type="omfile" dynaFile="TemplateRemoteBigIPAFM"   dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="2514" ruleset="remoteBigipAFM")

template(name="TemplateRemoteBigIPDoS"   type="string" string="/var/log/%fromhost%/dos.log")
ruleset(name="remoteBigipDoS"){   action(type="omfile" dynaFile="TemplateRemoteBigIPDoS"   dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="3514" ruleset="remoteBigipDoS")

template(name="TemplateRemoteBigIPBOT"   type="string" string="/var/log/%fromhost%/bot.log")
ruleset(name="remoteBigipBOT"){   action(type="omfile" dynaFile="TemplateRemoteBigIPBOT"   dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="4514" ruleset="remoteBigipBOT")

template(name="TemplateRemoteBigIPIPSEC" type="string" string="/var/log/%fromhost%/ipsec.log")
ruleset(name="remoteBigipIPSEC"){ action(type="omfile" dynaFile="TemplateRemoteBigIPIPSEC" dirCreateMode="0755" fileCreateMode="0644")}
input(type="imtcp" port="5514" ruleset="remoteBigipIPSEC")

```