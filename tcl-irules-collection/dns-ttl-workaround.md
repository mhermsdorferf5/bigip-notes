# DNS TTL Workaround

There's a bug in some versions of bind where Resource Records (RRs) with a TTL of 0 are cached for however long we are currently away from the unix epoc (as of 2025, 55 years).

That bug is documented here: https://gitlab.isc.org/isc-projects/bind9/-/issues/5094

## F5 BIG-IP Fix

F5 DNS Cache will respond with DNS TTL zero both if it receives a DNS TTL of zero from the upstream DNS server and if it's DNS TTL cache has reached zero but the record has not yet been cleared out of cache.  This is documented here: https://cdn.f5.com/product/bugtracker/ID741203.html

We can however, use an iRule to update any DNS TTL from zero to one in order to prevent triggering the bind bug.

### iRule

```tcl
when DNS_RESPONSE {
    foreach rr [DNS::answer] {
        if { [DNS::ttl $rr] == 0 } {
            DNS::ttl $rr 1
        }
    }
}
```

### iRule Performance

Processor CPU in Ghz:
2,200,000,000
(Note the i4800, has a 2.2ghz processor.)

If we assume the iRule has an average run cpu cycles of 71,600 cycles.  (As tested in the lab, see assumptions below.)

If we further assume we are processing around 1,000 DNS Queries per second:

(71,600/2,200,000,000)*1000 = 3.25% increase in CPU usage per every 1000 DNS responses per second.

The final assumption is that this will be RR set dependent, my testing is based on an average of 2.5 RRs per DNS request.
