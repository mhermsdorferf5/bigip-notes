################################################################################
################################################################################
# SNAT based on source address from data-group
# Create a data-group with the subnets to snat:
# tmsh create ltm data-group internal /Common/subnets_to_snat_dg type ip records replace-all-with { 10.53.24.0/24 10.53.28.0/22 10.53.48.0/22 }

when CLIENT_ACCEPTED {
    # Set the name of the data-group containing IPs/Subnets to SNAT:
    set subnets_to_snat_dg "/Common/subnets_to_snat_dg"

    # IF the data-group exists
    if { [class exists ${subnets_to_snat_dg}]} {
        # Check if the Client IP is within the data-group:
        if { [class match [getfield [IP::client_addr] "%" 1] equals ${subnets_to_snat_dg}]} {
            # SNAT the traffic:
            snat automap 
            # Note you can also snat to a specific ip and/or snatpool.
            # snat <ip>
            # snat <snatpool name>
        }
    }
}

################################################################################
################################################################################
# A sometimes handy alternative, for dynamic Selective SNAT
# This SNATs the traffic when a server on the same /24 subnet uses the VIP.
# If the client and the selected pool member are on the same /24 subnet
# then SNAT the traffic:
when LB_SELECTED {  
    if {[IP::addr "[getfield [IP::client_addr] "%" 1]/24" equals "[getfield [IP::server_addr] "%" 1]/24"]} {  
        snat automap 
        # Note you can also snat to a specific ip and/or snatpool.
        # snat <ip>
        # snat <snatpool name>
    }
}