# AS3 Performance Tunning and expectations

## Consideration Points & Recommendations

* The most important thing is bigger management plane memory (2GB + extra needed for config size and modules), bigger icrd (icrd is part of restjavad) memory.
  * Specific starting memory tunning recommendations below.
  * The best way to tune is to tail the restjavad.gc log and keep increasing restjavad memory it until the rate of gc events slows down, or if memory isn’t a concern start with a very large value 2g above is large.  You Ideally want to see less than a few gc events per second.
* Limit concurrency against the AS3 API.
  * If you don’t limit it externally to AS3, you can leverage burst handling to help: [AS3 Burst Handling](https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/userguide/burst-handling.html#burst)
* Don't use config autosync.
  * This is  highly recommended, autosync causes about a 6x reduction in performance.
  * Instead use manual sync, and add a 'syncToGroup' in the AS3 class of your declarations.
  * [AS3 Config Sync Docs](https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/userguide/faq.html#configsync)
  * [Schema Reference for as3 class](https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/refguide/schema-reference.html#as3)
* If config autosync is a must, then change the AS3 setting asyncTaskStorage to memory.
  * See: [AS3 Settings Endpoint Docs](https://clouddocs.f5.com/products/extensions/f5-appsvcs-extension/latest/userguide/settings-endpoint.html)
  * BIG-IP Config autosync is always synchronize replication, which is a problem from a performance standpoint.  Changing asyncTaskStorage from data-group to memory will lower the number of config changes while AS3 is working to deploy config in autosync mode and improve performance a little.
  * The downside of setting asyncTaskStorage to memory is that the work queue won’t be retained on reboot, so if you reboot in the middle of an AS3 deploy it won’t resume the task when it comes back up.  AS3 Decleration history is still retained in data-groups.
* Use a local admin account or token auth.
* Use BIG-IP 17.1.x or later.
* Do not crank the timeouts up beyond about 120-180 seconds above, this will only delay/cascade any problems.

Just as a reference, internal testing has shown that if you’re run 17.1.x, apply the DB keys below, use syncToGroup instead of autosync and you can deploy AS3 configs fast enough to kill mcpd/big-ip with more config objects than it can handle in about 20 minutes.  This is somewhere around 250,000 config objects.

## Recommended starting memory and timeout settings for large configs

* Note this requires an additional 3.5g of ram for the control plane.

```bash
tmsh modify /sys db provision.extramb value 1638
tmsh modify /sys db provision.restjavad.extramb value 2022
tmsh modify /sys db restnoded.timeout value 180
tmsh modify /sys db restjavad.timeout value 180
tmsh modify /sys db icrd.timeout value 180
tmsh modify /sys db iapplxrpm.timeout value 300
tmsh save sys config
tmsh restart sys service restjavad tomcat restnoded
```

## Recommended starting memory and timeout settings for smaller configs

* If you don't have the additional 3.5g of RAM to spare, and do not have terribly large configurations, consider these.

```bash
tmsh modify /sys db provision.extramb value 1024
tmsh modify /sys db provision.restjavad.extramb value 1024
tmsh modify /sys db restnoded.timeout value 180
tmsh modify /sys db restjavad.timeout value 180
tmsh modify /sys db icrd.timeout value 180
tmsh modify /sys db iapplxrpm.timeout value 300
tmsh save sys config
tmsh restart sys service restjavad tomcat restnoded
```

## Additional Supporting KB Articles

* [Management provisioning](https://my.f5.com/manage/s/article/K26427018)
* [Overview of restajavd/restnoded provisioning](https://my.f5.com/manage/s/article/K000137363)
* [restjavad memory provisioning](https://my.f5.com/manage/s/article/K000133258)
* [Icrd/restjavad/restnoded Timeouts](https://my.f5.com/manage/s/article/K94602685)
