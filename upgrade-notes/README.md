# BIG-IP Upgrade Notes

Collection of notes, documentation, etc useful for upgrading BIG-IP software.

## Review the following F5 Docs

* [K84554955: Overview of BIG-IP system software upgrades](https://my.f5.com/manage/s/article/K84554955)
* [K84205182: BIG-IP update and upgrade guide](https://my.f5.com/manage/s/article/K84205182)
* [K7727: License activation may be required before a software upgrade for BIG-IP](https://my.f5.com/manage/s/article/K7727)
* [K13845: Overview of supported BIG-IP upgrade paths and an upgrade planning reference](https://my.f5.com/manage/s/article/K13845)
* For GTM/DNS Sync Group Upgrades
  * [K11661449: Overview of BIG-IP DNS system software upgrades](https://my.f5.com/manage/s/article/K11661449)
  * As noted above, be sure to take the additional steps when upgrading GTM/DNS sync groups, as improper upgrade procedures can lead to a loss of the GSLB configuration.

## Example upgrade script

An example upgrade manual script can be found here: [sample upgrade script](sample.upgrade.script.md).  This document walks through the basic steps of getting pre-change backups, qkviews, and pool/virtual server state, along with the typical upgrade steps and post-change qkviews and virtual/pool states for comparison.

## Upgrades from BIG-IP pre-v14 to v14 or higher

A change in iRule validation may break iRules if using any of the following commands: HTTP::respond, HTTP::redirect, HTTP::retry.  For details see: [K23237429: TCL error: ERR_NOT_SUPPORTED after upgrade to version 14.1.0 or later](https://my.f5.com/manage/s/article/K23237429)
