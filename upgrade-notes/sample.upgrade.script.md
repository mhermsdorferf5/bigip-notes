# BIG-IP Example Upgrade Script

Example upgrade script for BIG-IP HA Pair, note this does not cover GSLB/GTM Sync Group Steps.  No impact to traffic occurs until the upgrade section, all pre-steps are impact free.

For full instructions see: [K84205182: BIG-IP update and upgrade guide](https://my.f5.com/manage/s/article/K84205182)

## Pre-Upgrade Data Collection & Verification

These steps should happen on all devices in the HA/DSC group.

### Verify base and any potential EHF ISO images in /shared/images, otherwise copy the files to the BIG-IP

* Confirm all needed base ISO images and EHF ISO files required for the upgrade are in /shared/images/
```ls -la /shared/images```

### Check service check date

* for v17.1.x this should a date after: 2023-02-08, for v15.1.x after: 2019-11-05
  * See: [K7727: License activation may be required before a software upgrade for BIG-IP](https://my.f5.com/manage/s/article/K7727)
* Critical: You MUST re-license the BIG-IP if the service check date in the license file is not newer than expected service check date for the version.

```grep "Service check date" /config/bigip.license```

Example Output

```bash
    grep "Service check date" /config/bigip.license
    Service check date :               20230624
```

### Count of current pool member & virtual server health

Obtain current count of virtual servers and pools, to compare post-upgrade.

```bash
tmsh -c 'cd /; show ltm pool recursive' | grep -i Availability | sort | uniq -c
tmsh -c 'cd /; show ltm virtual recursive' | grep -i Availability | sort | uniq -c
```

Write these numbers down in a safe place

### Record pre-change pool member health & virtual server health to TSV file

Obtain current health status of virtual servers and pools to compare post-upgrade.

```bash
tmsh -c 'cd /; show ltm pool recursive' | grep -iE "Ltm::Pool|Availability|Current Active Members" | perl -0777 -nle 'print "\/$1\t$2\t$3\n" while m/.*Ltm::Pool: (\S+)\s+Availability\s+:\s+(\S+)\s+Current Active Members\s+:\s+(\d+).*/gm' | sort > /var/tmp/pre-change_pool_status_`uname -n`_`date --rfc-3339=date`.tsv
tmsh -c 'cd /; show ltm virtual recursive' | grep -iE "Ltm::Virtual|Availability" | perl -0777 -nle 'print "\/$1\t$2\n" while m/.*Ltm::Virtual Server: (\S+)\s+Availability\s+:\s+(\S+)\s+/gm' | sort > /var/tmp/pre-change_virtual_status_`uname -n`_`date --rfc-3339=date`.tsv
```

### Save qkview and upload to iHealth

```bash
qkview -f /var/tmp/pre-change-qkview_`uname -n`_`date --rfc-3339=date`.qkview
```

Copy Qkview down from /var/tmp/, upload file to [iHealth](https://ihealth.f5.com), and attach to proactive support case.

### Save UCS backup and copy it off-box.

```bash
tmsh save sys ucs /var/tmp/pre-change-qkview_`uname -n`_`date --rfc-3339=date`.ucs
```

Copy UCS archive down from /var/tmp/, save somewhere safe in case it's needed.

## Pre-Upgrade Prep & Software Install

### Determine which boot location to install new software in

```bash
tmsh show sys software status
```

If there is only one boot location listed, then we'll install into HD1.2
If there are multiple boot locations listed, then we'll install into the non-active boot location.  This could be HD1.1 or HD1.2.

### Install new BIG-IP Software

If there was only one boot location on the previous step:
```bash
tmsh install sys software image <iso-image-file-name> location HD1.2 create-volume
```

If there were two boot locations:
```bash
tmsh install sys software image <iso-image-file-name> location <HD1.1/HD1.2 from previous step>
```

### Monitor BIG-IP Software installation status

```bash
watch tmsh show sys software status
```

## Upgrade

These steps start happening in the outage window

### Upgrade Standby BIG-IP

SSH into standby device and perform upgrade

```bash
cpcfg <boot location of new software install>
tmsh reboot volume <boot location of new software install>
```

For example, if the new software was installed into HD1.2:
```bash
cpcfg HD1.2
tmsh reboot volume HD1.2
```

Wait a minimum of 15min before expecting the standby box to come back online, longer if this is a chassis based system.  Upgrades can take some time, and may involve multiple reboots when installing upgraded firmware or FPGA bytecode.

Confirm the box comes up as online status and standby.

Confirm health checks are passing on the pools and that overview of VIPSs shows expected vips online & healthy.

### Failover to newly upgraded standby

SSH to the active device and run the following to failover traffic to the upgraded box.

```bash
tmsh run sys failover standby
```

### Confirm failover

On the upgraded device, confirm it's now Active and is showing increasing traffic counts.  Also, a good idea to do some quick spot checks of various VIPs, and to monitor the LTM logs for errors.

```bash
tmsh show sys failover
tmsh show sys traffic
tail -100f /var/log/ltm
```

### Upgrade previously active, now standby BIG-IP

SSH into previously active, now standby device and perform upgrade

```bash
cpcfg <boot location of new software install>
tmsh reboot volume <boot location of new software install>
```

For example, if the new software was installed into HD1.2:
```bash
cpcfg HD1.2
tmsh reboot volume HD1.2
```

Wait a minimum of 15min before expecting the standby box to come back online, longer if this is a chassis based system.  Upgrades can take some time, and may involve multiple reboots when installing upgraded firmware or FPGA bytecode.

Confirm the box comes up as online status and standby.

Confirm health checks are passing on the pools and that overview of VIPSs shows expected vips online & healthy.

## Post-Upgrade Data Collection

These steps should happen on all devices in the HA/DSC group.

### Count of current pool member & virtual server health

Obtain current count of virtual servers and pools, to compare with pre-upgrade.

```bash
tmsh -c 'cd /; show ltm pool recursive' | grep -i Availability | sort | uniq -c
tmsh -c 'cd /; show ltm virtual recursive' | grep -i Availability | sort | uniq -c
```

Compare counts with pre-upgrade counts saved previously.

### Record pre-change pool member health & virtual server health to TSV file

Obtain current health status of virtual servers and pools to compare with pre-upgrade.

```bash
tmsh -c 'cd /; show ltm pool recursive' | grep -iE "Ltm::Pool|Availability|Current Active Members" | perl -0777 -nle 'print "\/$1\t$2\t$3\n" while m/.*Ltm::Pool: (\S+)\s+Availability\s+:\s+(\S+)\s+Current Active Members\s+:\s+(\d+).*/gm' | sort > /var/tmp/post-change_pool_status_`uname -n`_`date --rfc-3339=date`.tsv
tmsh -c 'cd /; show ltm virtual recursive' | grep -iE "Ltm::Virtual|Availability" | perl -0777 -nle 'print "\/$1\t$2\n" while m/.*Ltm::Virtual Server: (\S+)\s+Availability\s+:\s+(\S+)\s+/gm' | sort > /var/tmp/post-change_virtual_status_`uname -n`_`date --rfc-3339=date`.tsv
```

### Save qkview and upload to iHealth

```bash
qkview -f /var/tmp/post-change-qkview_`uname -n`_`date --rfc-3339=date`.qkview
```

Copy Qkview down from /var/tmp/, upload file to [iHealth](https://ihealth.f5.com), and attach to proactive support case.

### Save UCS backup and copy it off-box.

```bash
tmsh save sys ucs /var/tmp/post-change-qkview_`uname -n`_`date --rfc-3339=date`.ucs
```

Copy UCS archive down from /var/tmp/, save somewhere safe in case it's needed.

## Post-Upgrade Health Checks

These steps should happen on all devices in the HA/DSC group.

### Compare iHealth counts pre & post upgrade

Use ihealth summary screen to obtain count of virtual servers, pools, pool members, and health monitor isntance count.  Confirm that these match pre & post change.

### Compare health status between pre & post upgrade

Use the diff command to compare pre change and post change health status information:

```bash
diff /var/tmp/pre-change_pool_status_`uname -n`_`date --rfc-3339=date`.tsv /var/tmp/post-change_pool_status_`uname -n`_`date --rfc-3339=date`.tsv
diff /var/tmp/pre-change_virtual_status_`uname -n`_`date --rfc-3339=date`.tsv /var/tmp/post-change_virtual_status_`uname -n`_`date --rfc-3339=date`.tsv
```

Ideally you should see no differences, however note that if the application team is doing maintenance as well you may see some differences in health status.
