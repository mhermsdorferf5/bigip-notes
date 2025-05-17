# SSH Proxy Config Example

[Official SSH Proxy Documentation](https://techdocs.f5.com/kb/en-us/products/big-ip-afm/manuals/product/network-firewall-policies-implementations-12-1-0/13.html)
[AFM Logging Configuration](https://my.f5.com/manage/s/article/K03094407)

```
### Virtual Server and Pool
ltm virtual /Common/ssh-proxy-test {
    destination /Common/10.12.0.177:22
    mask 255.255.255.255
    ip-protocol tcp
    pool /Common/herm-nginx-ssh
    profiles {
        /Common/tcp { }
        /Common/ssh-proxy { }
    }
    security-log-profiles {
        /Common/ssh-afm-local
    }
    serverssl-use-sni disabled
    source 0.0.0.0/0
    source-address-translation {
        type automap
    }
    translate-address enabled
    translate-port enabled
}
ltm pool /Common/herm-nginx-ssh {
    members {
        /Common/10.12.0.14:22 {
            address 10.12.0.14
        }
    }
    monitor /Common/tcp
}


### SSH Proxy Profile:
security ssh profile /Common/ssh-proxy {
    actions {
        actions {
            agent-action {
                log yes
            }
            local-forward-action {
                log yes
            }
            other-action {
                log yes
            }
            remote-forward-action {
                log yes
            }
            rexec-action {
                log yes
            }
            scp-down-action {
                log yes
            }
            scp-up-action {
                log yes
            }
            sftp-down-action {
                log yes
            }
            sftp-up-action {
                log yes
            }
            shell-action {
                log yes
            }
            sub-system-action {
                log yes
            }
            x11-forward-action {
                log yes
            }
        }
    }
    app-service none
    auth-info {
        herm-nginx2 {
            proxy-server-auth {
                private-key <redacted>
                public-key AAAAB3NzaC1yc2EAAAADAQABAAACAQDL2SPAO8dVdOvxXgYmEHExDeMBZI9bkgbL4PRHZ3+0IdO/C2CXpT02q2qHZM+X59V1/p6gt7r6HGdbW0afLjYavY6t1VB5cEA5LbzyqC0Rm3zJO2xn6Vdlq9cqqSALbXah8CgvyOp6i72OF2Qi1oZqvpf37DWmjz7JdZPwO42BUf5IdAtV5rFE6Zy6v1uYhAENrs0p1kcplf/5skK5Z1f1qjS5a4n5hI7mMtOvA9xZQf0cAvUCWOKUSjUXb//fYr1X9MHQ9n15+JpmKfnlAaMoFmpTu3q8ku2O47cqVNZc1wnuHCgNyi4qNCD8PwxiKdeWScGTboLXETCrztjxVMzF1q0TGPG4OKadEWRX9QG4Zt9yCa4mXDb573A9Fm/xb3OfCT/MKvyGDo8f/M8Etz+4FRdkvEQY+L6hlPZzeFdSIY/8FRQ6KApVrrnzFkbIJ3xgz9lq+tB6A/quapWc1phc08RZqJNSyn2JWDoidUb2XKJtAcgBQOwujVDQ/MgMQUo9IbxU+IU5w6ZXjNS1BU7ZSK0y8S2fj8tqIeQqVHjRTLI6o4U5BaaANeGqptj56Gc6SFuYYPmZ2dvIm8b7wC1FNwidzohKMaKrmtqJ3Q1c1ZahHj9HOej/LjxXTROjZKcVIyGf3vVJZs21x/GyRvQBMcAyr7HVTsbFU9MTdGZNfQ==
            }
            real-server-auth {
                public-key AAAAB3NzaC1yc2EAAAADAQABAAABgQCYyBw4/ZZs6hU9ML7t6j0+EfDURG0bZSFuV8+Ojv5LZr8u8QWz0DQPgee5tVMlO/6ZXUAiYKgSwgEMRlzn6N9jM6V9PnuJtTW6c4Wndqa0G2Lse6BZZ3ONCz7DT4NOMYJ66pv0QIEb118P6z90loebglDjDLuPFdF46wkxalmlSf8GcJ9yxXyl15WzkdhBLW4YToOdJJM/NQxvbnQvM/Hzt4CD3oyvnXBlrfvXzhZgYoh8jEcsNSaCDrdJdmDUxFhOiemH8NDeFgikfWHtPqEFPa0dm/I8UeO1KHm5TwwB1qdBAymkjjgSis4ANE3EaupMyumkU4KU97UMq8K7e5AYmZr33zuAeUdSZdce4EqqSsPrRchVr99aBh1oeX/a295k3MK3uhCpn2QxugvYYnAUUCr9/IqEQWPGVynpi8pUbxayTpTWK0QEG4Pl0UXQT+bs9zloQ1Y49QuxUryUwWNSegJ6J6oHsr4pTRBCeaBW4B9o9XLX7nTktBxQQmfSEDk=
            }
        }
    }
    description none
    lang-env-tolerance common
    timeout 0
}


## LOGGING:
security log profile /Common/ssh-afm-local {
    ssh-proxy {
        /Common/ssh-afm-local {
            allowed-channel-action enabled
            disallowed-channel-action enabled
            log-publisher /Common/local-syslog-publisher
            non-ssh-traffic enabled
            partial-client-side-auth enabled
            partial-server-side-auth enabled
            ssh-timeout enabled
            successful-client-side-auth enabled
            successful-server-side-auth enabled
            unsuccessful-client-side-auth enabled
            unsuccessful-server-side-auth enabled
        }
    }
}
```
