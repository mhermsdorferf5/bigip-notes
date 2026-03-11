ltm data-group internal rfc1918 {
    records {
        10.0.0.0/8 { }
        172.16.0.0/12 { }
        192.168.0.0/16 { }
    }
    type ip
}
ltm policy drop-non-internal {
    requires { tcp }
    rules {
        reset-non-internal-traffic {
            actions {
                0 {
                    shutdown
                    client-accepted
                    connection
                }
            }
            conditions {
                0 {
                    tcp
                    client-accepted
                    address
                    not
                    matches
                    datagroup /Common/rfc1918
                }
            }
        }
    }
    status published
    strategy first-match
}