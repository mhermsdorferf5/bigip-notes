# v1.00 - initial release
# v1.01 - moved logging to a procedure id1354253_logger and added HTTP host header to log by default
# v1.02 - rate limited logging by removing facility from call to log, see https://clouddocs.f5.com/api/irules/log.html for more info
# v1.03 - moved header value normalization to proc normalize_header_list to reduce code complexity
# v1.04 - added support for remote logging via HSL
# v1.05 - added checking for last T-E/C-L header being empty; removed static global vars.
# v1.06 - added check for K23237429; with HTTP::has_responded, in case LTM policies redirect first.

# All logs are in the following format - change as you see fit
# MsgID,Client IP,Server Name,HTTP Host header value,Note
# e.g.,
# 100,10.0.0.1,Test_VS_443,www.example.com,"Warning: Multiple (2) Transfer-Encoding headers found"

# 100 - Multiple T-E headers found
# 200 - Multiple C-L headers found
# 101 - Invalid T-E header value not one of validTransferEncodings
# 102 - Invalid T-E header value (chunked not last value or value of last T-E header)
# 201 - Empty C-L (C-L failed to parse or is 0)
# 202 - Invalid C-L (C-L not integer value)
# 203 - Invalid C-L (C-L has non-identical multiple values)
# 300 - Suspect header smuggling (colon found in header value)
# 401 - Last T-E header is empty value.
# 402 - Last C-L header is empty value.

when CLIENT_ACCEPTED {
    # Set to 1 to log locally, 0 to log to HSL. If setting to 0 you MUST set the HSL target as well
    set local_logging 1
    # hsl_target must be a Log Publisher configured in System->Logs->Configuration->Log Publishers
    # see https://clouddocs.f5.com/api/irules/HSL__open.html for more info
    set hsl_target /Common/remotepub
    # This is the list of valid Transfer-Encodings for ID1354253
    set validTransferEncodings [list chunked compress deflate gzip]
    
    if {$local_logging < 1} {
        if { [catch {HSL::open -publisher $hsl_target } hsl] } {
            log "Failed to open HSL to ${hsl_target} publisher."
            set hsl ""
        }
    } else {
        # Local logging set HSL to 0.
        set hsl "0"
    }
}

proc id1354253_logger {code msg hslconn} {
    # 190 is local7.info, see https://datatracker.ietf.org/doc/html/rfc3164#section-4.1.1 for others
    set hsl_priority "<190>"
    # Conditionally log locally to /var/log/ltm or HSL
    # Consider logging remotely using HSL (see https://clouddocs.f5.com/api/irules/HSL.html) on production
    # or high-volume systems
    set logMessage "$code,[IP::client_addr],[virtual name],[HTTP::host],\"$msg\""
    if {$hslconn == 0} {
        log $logMessage
        # Comment the above and uncomment the below to log without rate limiting
        # log local0. $logMessage
    } elseif {$hslconn != "" } {
        HSL::send $hslconn "$hsl_priority $logMessage"
    }
}

proc normalize_header_list {hdrvals} {
    foreach hdrVal $hdrvals {
        if {$hdrVal contains ","} {
            set hdrValNorm [split $hdrVal ","]
            foreach innerVal $hdrValNorm {
                lappend normalizedValues [string trim $innerVal]
            }
        } else {
            lappend normalizedValues [string trim $hdrVal]
        }
    }

    return $normalizedValues
}

when HTTP_REQUEST priority 1 {

    # If an LTM Policy has redirected, we must bail, as no HTTP objects will be valid
    # see: https://my.f5.com/manage/s/article/K23237429
    if { [HTTP::has_responded] } { return }
    
    set requestMethod [HTTP::method]
 
    # Check if there >1 Transfer-Encoding headers, warn if so as some of our checks are not 100% per ID1354253
    if {[HTTP::header count Transfer-Encoding] > 1} {
        call id1354253_logger "100" "Warning: Multiple ([HTTP::header count Transfer-Encoding]) Transfer-Encoding headers found" $hsl
    }
 
    # Check if there are >1 Content-Length headers, warn if so as some of our checks are not 100% per ID1354253
    if {[HTTP::header count Content-Length] > 1} {
        call id1354253_logger "200" "Warning: Multiple ([HTTP::header count Content-Length]) Content-Length headers found" $hsl
    }
 
    # With mulitple T-E headers we get a list back, but if any of those headers have multiple values we have
    # a mix of comma-separated values (which should be a list) and list entries, so we need to normalize them
    if {[HTTP::header count "Transfer-Encoding"] >= 1} {
        set transferEncodingValues [HTTP::header values "Transfer-Encoding"]
        set transferEncodingNormalizedValues [call normalize_header_list $transferEncodingValues]

        # Check that normalized T-E values contain only compress, deflate, gzip or chunked, or combinations of
        # and that chunked is the last value
        # It is possible to fool this, but it's as close as we can get in iRules; ID1354253 says that if "chunked" is present
        # it must be the last one in a comma-separated list, or be only value in the last Transfer-Encoding header, but
        # here we only check if it is the last value, we don't guarantee it is alone in the last header
        foreach encodingValue $transferEncodingNormalizedValues {
            if {!([lsearch -exact $validTransferEncodings $encodingValue] >= 0)} {
                call id1354253_logger "101" "Request with invalid Transfer-Encoding header value, $encodingValue" $hsl
            }
 
            # Check that chunked is always last, if present
            if {$encodingValue eq "chunked"} {
                if {[lsearch -exact $transferEncodingNormalizedValues $encodingValue] != [llength $transferEncodingNormalizedValues] - 1} {
                    set telength [llength $transferEncodingNormalizedValues]
                    set tepos [lsearch -exact $transferEncodingNormalizedValues $encodingValue]
                    call id1354253_logger "102" "Request with invalid Transfer-Encoding header order, $encodingValue is not last of $telength item list but $tepos instead" $hsl
                }
            }
        }
    }
 
    # With mulitple C-L headers we get a list back, but if any of those headers have multiple values we have
    # a mix of comma-separated values (which should be a list) and list entries, so we need to normalize them
    if {[HTTP::header count "Content-Length"] >= 1} {
        set contentLengthValues [HTTP::header values "Content-Length"]
        set contentLengthNormalizedValues [call normalize_header_list $contentLengthValues]

        # Check that normalized C-L values are positive integers only and do not contain any non-numeric characters (e.g., hex etc is not allowed)
        # and if a list of C-L values is provided then all C-Ls should be identical in value
        # This is extremely difficult to test for in iRules thanks to how TCL handles type-less variables, so this
        # is a close analog, ensuring that CL isn't empty and is a positive number which does not include any non
        # numeric characters (e.g., no hex encoding, alpha etc)
        set lastClVal 0
        foreach clVal $contentLengthNormalizedValues {
            if {($clVal eq "" || $clVal < 0) && ([string tolower [HTTP::header names]] contains "content-length")} {
                call id1354253_logger "201" "Request with empty Content-Length" $hsl
            }
 
            if {(![string is double -strict $clVal] || [string match "*+*" $clVal] || [string match "*-*" $clVal] || [string match "*.*" $clVal] || [string match "*x*" $clVal]) && $clVal ne ""} {
                call id1354253_logger "202" "Request with invalid Content-Length: $clVal" $hsl
            }
 
            if {($clVal ne $lastClVal) && ($lastClVal ne 0)} {
                call id1354253_logger "203" "Request with multiple Content-Length values, but values are not identical: $clVal != $lastClVal" $hsl
            }
            set lastClVal $clVal
        }
    }
 
    # This check ensures the HTTP parser has not been abused by checking to ensure that no header _value_ contains
    # ':', e.g., a complete "header: value" pair has not been smuggled in the CL or TE header
    foreach header [HTTP::header names] {
        set header_value [HTTP::header values $header]
 
        if { (([string tolower $header_value] contains "content-length") ||
        ([string tolower $header_value] contains "transfer-encoding")) &&
        ([string first ":" $header_value] >= 0) } {
            call id1354253_logger "300" "Request from [IP::client_addr] due to presence of suspect header value of $header" $hsl
        }
    }

    # This checks if the last C-L or T-E header contains no value.
    if {[HTTP::header count "Transfer-Encoding"] >= 1} {
        # HTTP::Header value pulls the last value from the list of headers, per F5 docs.
        if { [string trim [HTTP::header value "Transfer-Encoding"]] == "" } {
            call id1354253_logger "401" "Request from [IP::client_addr] due to last Transfer-Encoding header being empty." $hsl
        }
    }
    if {[HTTP::header count "Content-Length"] >= 1 } {
        # HTTP::Header value pulls the last value from the list of headers, per F5 docs.
        if { [string trim [HTTP::header value "Content-Length"]] == "" } {
            call id1354253_logger "402" "Request from [IP::client_addr] due to last Content-Length Header being empty." $hsl
        }
    }

 
    unset -nocomplain requestMethod transferEncodingValues teVal teValNorm innerVal transferEncodingNormalizedValues encodingValue
    unset -nocomplain contentLengthValues clVal clValNorm contentLengthNormalizedValues lastClVal header header_value hsl
}