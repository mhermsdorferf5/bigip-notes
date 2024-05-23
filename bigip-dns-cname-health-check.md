# DNS CNAME Failover Configuration

BIG-IP DNS doesn't allow you to natively do health checks on CNAME pools.  You can however leverage LTM config in order to get this ability, with a workaround.  This requires both LTM & DNS licensing of course.

In the following example, we have a site "dev.example.com" which can be served from two different target CNAMES:
dev.cdn.example.com
dev.dc1.example.com

If dev.cdn.example.com is workign, all traffic should go there, if it's down, all traffic should go to dev.dc1.example.com.
 
## Create LTM Monitors to monitor the endpoints, these can be used from a DNS/GTM only device:
* In the GUI these will show up under: DNS => Delivery => Load Balancing => Monitors
tmsh create ltm monitor https https-monitor-for_dev.example.com { defaults-from https send "GET / HTTP/1.1\r\nHost: dev.example.com\r\nUser-Agent: f5-health-monitor/1.0\r\nConnection: close\r\n\r\n" recv "HTTP/1\.\d " interval 5 timeout 16 }
 
## Create LTM Pools, again you can do this on GTM/LTM only device.
* In the GUI these will show up under: DNS => Delivery => Load Balancing => Pools
tmsh create ltm pool monitor-pool-for_dev.cdn.example.com { members replace-all-with { dev.cdn.example.com:443 { fqdn { autopopulate enabled name dev.cdn.example.com } } } monitor https-monitor-for_dev.example.com }
tmsh create ltm pool monitor-pool-for_dev.dc1.example.com { members replace-all-with { dev.dc1.example.com:443 { fqdn { autopopulate enabled name dev.dc1.example.com } } } monitor https-monitor-for_dev.example.com }
 
## Create LTM VIPs, again you can do this on GTM/LTM only device.
* In the GUI these will show up under: DNS => Delivery => Listiners
tmsh create ltm virtual dummy-monitor-vip-for_dev.cdn.example.com { destination 192.0.2.1:5353 pool monitor-pool-for_dev.cdn.example.com ip-protocol udp profiles replace-all-with { dns udp } }
tmsh create ltm virtual dummy-monitor-vip-for_dev.dc1.example.com { destination 192.0.2.2:5353 pool monitor-pool-for_dev.dc1.example.com ip-protocol udp profiles replace-all-with { dns udp } }

## Create LTM vips on GTM Server Objects:
* NOTE: You can skip this step if the GTM server object has virtual server discovery enabled.
tmsh modify gtm server <gtm-server-object-name> { virtual-servers add { /Common/dummy-monitor-vip-for_dev.cdn.example.com { destination 192.0.2.1:5353 } } }
tmsh modify gtm server <gtm-server-object-name> { virtual-servers add { /Common/dummy-monitor-vip-for_dev.dc1.example.com { destination 192.0.2.2:5353 } } }
 
## Create GTM Pools for GTM to monitor the dummy vips.
tmsh create gtm pool a monitor-pool-for_dev.cdn.example.com { members replace-all-with { <gtm-server-object-name>:/Common/dummy-monitor-vip-for_dev.cdn.example.com { member-order 0 } } }
tmsh create gtm pool a monitor-pool-for_dev.dc1.example.com { members replace-all-with { <gtm-server-object-name>:/Common/dummy-monitor-vip-for_dev.dc1.example.com { member-order 1 } } }
 
## Create GTM WIPS for GTM to monitor the dummy vips and report status to CNAME pool/WIP.
tmsh create gtm wideip a dev.cdn.example.com { pools replace-all-with { monitor-pool-for_dev.cdn.example.com { order 0 } } }
tmsh create gtm wideip a dev.dc1.example.com { pools replace-all-with { monitor-pool-for_dev.dc1.example.com { order 0 } } }
 
## Create CNAME pool referencing GTM Wide IPs we created to monitor our destinations:
tmsh create gtm pool cname dev.example.com { load-balancing-mode global-availability members replace-all-with { dev.dc1.example.com { member-order 0 } dev.cdn.example.com { member-order 1 } } }
 
## Create CNAME WideIP for our real domain name:
tmsh create gtm wideip cname dev.example.com { pools replace-all-with { dev.example.com { order 0 } } }
