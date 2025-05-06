when CLIENT_ACCEPTED priority 500 {

    # If we want to log to HSL, set this to 1, otherwise set to 0:
    # NOTE: if using HSL you *MUST* also set the HSL pool name below.
    set whitelist_log_hsl 0
    set whitelist_log_hsl_pool "/Common/whitelist_log_hsl_pool"
    
    # For local logging, set this to 1, otherwise set to 0:
    # Note: Local Logging is discouraged for production systems, as it can cause performance issues.
    set whitelist_log_local 1

    # To log all PUT requests, set this to 1, otherwise set to 0:
    set whitelist_log_all 1


    # IF we're logging to HSL, open the HSL handle:
    if { $whitelist_log_hsl } {
        set whitelist_log_hsl_handle [HSL::open -proto TCP -pool $whitelist_log_hsl_pool]
    }

    # Should we log only, or log and block:
    # Set to 0 to log only, 1 to log and block:
    set whitelist_blocking 1

    # Set to 0 to allow unknown object storage requests, 1 to block unknown object storage requests:
    set unknown_put_blocking 0

    # Set the name of the data-group containing whitelisted AWS buckets:
    set aws_dg "/Common/object_storage_whitelist_aws_dg"
    # set the name of the data-group containing whtielisted OCI namespaces:
    set oci_dg "/Common/object_storage_whitelist_oci_dg"
    # set the name of the data-group containing whtielisted Azure accounts::
    set azure_dg "/Common/object_storage_whitelist_azure_dg"
}

proc log_msg { str } {
    upvar whitelist_log_hsl whitelist_log_hsl
    upvar whitelist_log_local whitelist_log_local
    upvar whitelist_log_hsl_handle whitelist_log_hsl_handle
    set logPrefix "\"Client\"=\"[IP::client_addr]:[TCP::client_port]\", \"Server\"=\"[IP::server_addr]:[TCP::server_port]\""
    set logPrefix "$logPrefix, \"Method\"=\"[HTTP::method]\""
    set logPrefix "$logPrefix, \"Host\"=\"[HTTP::host]\", \"URI\"=\"[HTTP::uri]\""
    set logPrefix "$logPrefix, \"User-Agent\"=\"[HTTP::header value User-Agent]\""

    set logMsg "$logPrefix, \"LogMsg\"=\"$str\""

    if { $whitelist_log_hsl } {
        HSL::send $whitelist_log_hsl_handle "$logMsg"
    }

    if { $whitelist_log_local } {
        log local0. "$logMsg"
    }
}
proc log_action { action type bucket } {
    upvar whitelist_log_hsl whitelist_log_hsl
    upvar whitelist_log_local whitelist_log_local
    upvar whitelist_log_hsl_handle whitelist_log_hsl_handle
    set logPrefix "\"Client\"=\"[IP::client_addr]:[TCP::client_port]\", \"Server\"=\"[IP::server_addr]:[TCP::server_port]\""
    set logPrefix "$logPrefix, \"Method\"=\"[HTTP::method]\""
    set logPrefix "$logPrefix, \"Host\"=\"[HTTP::host]\", \"URI\"=\"[HTTP::uri]\""
    set logPrefix "$logPrefix, \"User-Agent\"=\"[HTTP::header value User-Agent]\""

    set logMsg "$logPrefix, \"Action\"=\"$action\", \"Type\"=\"$type\", \"Bucket\"=\"$bucket\""

    if { $whitelist_log_hsl } {
        HSL::send $whitelist_log_hsl_handle "$logMsg"
    }

    if { $whitelist_log_local } {
        log local0. "$logMsg"
    }
}



when HTTP_REQUEST priority 500 {
    set obj_type "unknown"
    set allow 0
    set bucket_name "unknown"

    # All Object storage requests that upload files start with a PUT request.
    if { [HTTP::method] equals "PUT" } {

        switch -glob -- [string tolower [HTTP::host]] {
            "s3.amazonaws.com" -
            "s3.*.amazonaws.com" {
                set obj_type "aws"
                # bucket name the first element of the path, use string map to remove the leading & trailing /:
                # set bucket_name [string map { / "" } [URI::path [HTTP::path] 1 2] ]
                # bucket name is the first element of the path:
                set bucket_name [lindex [split [HTTP::path] "/"] 0]
            }
            "*.s3.amazonaws.com" -
            "*.s3.*.amazonaws.com" {
                set obj_type "aws"
                # bucket name the first element of the hostname:
                set bucket_name [lindex [split [HTTP::host] "."] 0]
            }
            "*.compat.objectstorage.*.oci.com" -
            "*.compat.objectstorage.*.oraclecloud.com" {
                set obj_type "oci"
                # bucket name is the first element of the hostname:
                set bucket_name [lindex [split [HTTP::host] "."] 0]
            }
            "objectstorage.*.oraclecloud.com" -
            "objectstorage.*.oci.com" {
                set obj_type "oci"
                # bucket name is the second element of the path:
                set bucket_name [lindex [split [HTTP::path] "/"] 1]
            }
            "*.blob.core.windows.net" {
                set obj_type "azure"
                # bucket name is the first element of the hostname:
                set bucket_name [lindex [split [HTTP::host] "."] 0]
            }
        }

        switch $obj_type {
            "aws" {
                if { [class exists $aws_dg] } {
                    if { [class match $bucket_name contains $aws_dg] } {
                        set allow 1
                    }
                } else {
                    call log_msg "AWS bucket whitelist data-group not found."
                }
            }
            "oci" {
                if { [class exists $oci_dg] } {
                    if { [class match $bucket_name contains $oci_dg] } {
                        set allow 1
                    }
                } else {
                    call log_msg "OCI bucket whitelist data-group not found."
                }
            }
            "azure" {
                if { [class exists $azure_dg] } {
                    if { [class match $bucket_name contains $azure_dg] } {
                        set allow 1
                    }
                } else {
                    call log_msg "Azure bucket whitelist data-group not found."
                }
            }
            "unknown" {
                call log_msg "Unknown object storage type."
            }
        }

        if { $unknown_put_blocking == 0 && $obj_type == "unknown" && $bucket_name == "unknown" } {
            set allow 1
        }

        if { $allow == 0 } { 
            if { $whitelist_blocking == 1 } {
                call log_action "block" "$obj_type" "$bucket_name"
                HTTP::respond 403 content "Access Denied" reason "Forbidden"
            } else {
                call log_action "staged-block" "$obj_type" "$bucket_name"
            }
        }
    }
}