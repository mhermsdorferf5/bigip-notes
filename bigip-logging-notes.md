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
