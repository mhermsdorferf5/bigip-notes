# This iRule logs the TLS session id & secret, 
# this can be feed into wireshark to decrept traffic.
# use the following command to generate a sessionsecets.pms file for wireshark:
# sed -e 's/^.*\(RSA Session-ID\)/\1/;tx;d;:x' /var/log/ltm > /var/tmp/sessionsecrets.pms
# See: https://support.f5.com/csp/article/K12783074

# Note, if you're on v15.1.0 or higher you may not need this.
# tcpdump captures can be taken directly, capturing the tls sessionid & secret out of TMM
# See: https://support.f5.com/csp/article/K31793632

when CLIENTSSL_HANDSHAKE {
  if { [IP::addr [getfield [IP::client_addr] "%" 1] equals <client_IP_addr>] } {
    log local0. "[TCP::client_port] :: RSA Session-ID:[SSL::sessionid] Master-Key:[SSL::sessionsecret]"
  }
}

when SERVERSSL_HANDSHAKE {
  if { [IP::addr [getfield [IP::client_addr] "%" 1] equals <client_IP_addr>] } {
    log local0. "[TCP::client_port] :: RSA Session-ID:[SSL::sessionid] Master-Key:[SSL::sessionsecret]"
  }
}