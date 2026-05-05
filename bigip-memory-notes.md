# BIG-IP TMOS Memory Management Notes

This only applies to modern BIG-IP, v17.1 and above (up to v21.x as of the time of this writing).

## Intro

TMOS memory management can be painful and not terribly transparent from the documentation.  The first thing to remember is that TMOS disables linux's Transparent HugePage support (THP), this means that we have to manually manage the memory allocation between hugepages and non-hugepage memory.  As to why, THP is disabled I'm honestly not sure, I suspect history tells the story.  TMOS was released in 2004 before hugepages were all that common, while THP came along in 2011.

4KB Memory Pages are 'normal' or non-huge; this is used by *most* things in the management/linux plane.
2MB Huge memory pages are used by TMM, as well as some other management/linux plane processes.

In TMOS, on first boot 80-90% of memory is made into hugepages as though it was LTM dedicated.  Then the actual provisioning is read and some of this is released back to 4KB page memory as necessary.  As an example, with ASM provisioned you'd expect a 50/50 split, with ltm only more like a 80/20 to 90/10 split hugepages/non-hugepages.

## Useful Public Articles

[K000137363](https://my.f5.com/manage/s/article/K000137363): Overview of restjavad memory provisioning on BIG-IP and use of restjavad.useextramb, provision.extramb and provision.restjavad.extramb

[K000133258](https://my.f5.com/manage/s/article/K000133258): Provisioning restjavad memory with provision.restjavad.extramb

[K00505373](https://my.f5.com/manage/s/article/K00505373): Automation Toolchain restjavad extra memory allocation guidance (WARNING: This is not fully accurate, for example any addition toprovision.restjavad.extramb *must* be accompanied by an equal or larger addition to  provision.extramb)

## Manually modifying the HugePage/Non-HugePage split (provision.extramb)

This is controlled by the sys db: provision.extramb

A very simplistic explanation is that HugePage == DataPlane(TMM) and Non-HugePage == ManagementPlane(everything else), this isn't fully accurate but is a good rule of thumb.

This sysdb variable adjusts the divide between hugepage and 4KB page memory.  It's effectively adding the value set here, to the systems's already calculated pool of non-hugepage memory.  Remember, provisioning starts with the assumption that nearly all memory should be hugepages for TMM, then starts allocating more non-hugepage memory as provisioning would call for it.  So on an LTM only box, the value of provision.extramb will have a proportionally large impact because by default the vast majority (80-90%) of memory will be hugegpages.  While on an ASM provisioned device, the value of provision.extramb will have a proportionally smaller impact as the default provisoning is closer to 50/50 split of hugepages to non-hugepages.

NOTE: Changes to provision.extramb causes TMM/DataPlane service impact.  For this reason you typically want to over provision provision.extramb while you play with other non-dataplane impacting provisioning such as restjavad and tomcat extramb.

## Management Plane provisioning

Controlling the HugePage/non-HugePage split is critical to management plane memory provisioning.  It's a little too simplistic to say that HugePage == DataPlane(TMM) and Non-HugePage == ManagementPlane(everything else), but that's a 30k foot view.

Before adjusting these values you *must* make sure whatever additional memory you add here is already accounted for with provision.extramb as java only uses non-hugepages.

Neither of these cause service impact, however adjustments to provision.extramb does cause service impact.  For this reason you typically want to over provision provision.extramb while you play with restjavad and tomcat provisioning.

### provision.restjavad.extramb

This directly controls the java heap size for restjavad.  You *must* make sure whatever additional memory you add here is already accounted for with provision.extramb as java only uses non-hugepages.

If you're using any of the A&O toolchain tools such as: AS3, Declarative Onboarding, or Telemetry Streaming; you will want to over provision this.  If you're using A&O toolchain and have large configs, this could easily benefit from setting it to 2GB.

### provision.tomcat.extramb

This directly controls the java heap size for tomcat.  You *must* make sure whatever additional memory you add here is already accounted for with provision.extramb as java only uses non-hugepages.

If ASM is provisioned you typically don't need to tweak this too much as ASM allocates an additional 130 MB to tomcat.  If you don't have ASM provisioned, and you have particularly large configurations it can be useful to add 130 to 260 MB here.

## ASM/WAF related memory provisioning knobs

COMING SOON

## AFM related memory provisioning knobs

The following AFM sys db's control AFM memory management: provision.afm.extramb & pccd.extramb

Some additional details can be found in this kb article: [K000148866](https://my.f5.com/manage/s/article/K000148866)

The maximum blob size, in MB, is calculated when pccd starts.  The max blob size will be limited to 25% of "provision.memory.afm.host" or "pccd.maxblobsize", whichever is smaller.  In addition to this, 1/2 of "pccd.extramb" will be added to the limit.

MIN(provision.memory.afm.host/4, pccd.maxblobsize) + pccd.extramb/2

Like with other modules if you increase provision.extramb you lower the module specific amounts of non-hugepage memory, provision.memory.afm.host in this case. So that will lower the maximum BLOB size.

provision.afm.extramb may be used to compensate for that to make provision.memory.afm.host big enough so that it is pccd.maxblobsize that determines BLOB size.

You can determine the maximum blob side needed by looking at pccd logs: ```grep "BLOB Size" /var/log/pccd* | awk '{print $3}' | sort -n | tail -1```

### provision.afm.extramb

This will modify the HugePage/non-HugePage split in addition to giving various AFM processes additional memory.  There's no need to account for provision.extramb when modifying this sys db.

### pccd.extramb

This is used in computing the maximum blob size, but the documentation is very weak to non-existent.  It doesn't appear to have any impact on the hugepage split nor does PCCD doesn't use hugepages, but it also doesn't appear to have a bearing on how much memory pccd uses, but is only used in figuring the maximum blob size.

## Analysis Tool

I create a memory analysis tool that can provide some rather useful parsing of /proc/memstat and looks at the various processes to see what processes are using HugePages and how much HugePages vs. non-HugePages they use.  This can be helpful in both understanding what's going on and in figuring out how to tweak your memory provisioning settings optimally.

You can find the script here: [bigip-memory-tool.py](bigip-memory-tool.py)

An example of it being used on a big-ip:

```bash
[root@herm-bigip-v17-5:Active:Standalone] config # python3 bigip-memory-tool.py

===========================================================
  Memory Overview
===========================================================
  Total RAM:                             41.27 GB
  HugePage pool:                         27.28 GB  ( 66.1% of RAM)
  Non-HugePage pool:                     13.99 GB  ( 33.9% of RAM)

--- HugePage Memory ----------------------------------------
  HugePage size:                          2.00 MB
  HugePages total (count):                 13,966  ( 66.1% of RAM)
  HugePages used:                        27.24 GB  ( 99.9% of HugePage pool)
  HugePages reserved (not yet used):         0 KB  (  0.0% of HugePage pool)
  HugePages available:                   40.00 MB  (  0.1% of HugePage pool)

--- Non-HugePage Memory ------------------------------------
  Total non-hugepage pool:               13.99 GB  ( 33.9% of RAM)
  Used (excl. buffers/cache):             3.35 GB  ( 24.0% of non-HP pool)
  Buffers + cache (reclaimable):          4.45 GB  ( 31.8% of non-HP pool)
  Free:                                   6.19 GB  ( 44.2% of non-HP pool)
  Available (incl. reclaimable):          6.94 GB  ( 49.6% of non-HP pool)

--- Process HugePage Usage ---------------------------------
      PID  Name                        HugePage      %    Non-HugePage      %       Total RSS
  -----------------------------------------------------------------------------------------------
    11863  tmm.0                       27.24 GB  87.8%         3.77 GB  12.2%        31.01 GB
     6905  mgmt_acld                    1.00 GB  86.2%       164.51 MB  13.8%         1.16 GB
     7887  avrd                         1.00 GB  48.4%         1.07 GB  51.6%         2.07 GB
     9288  dwbld                        1.00 GB  77.6%       296.29 MB  22.4%         1.29 GB

  400 other processes using only 4KB pages, total RSS: 30.23 GB  (use --all-procs to list)
```
