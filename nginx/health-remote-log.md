# POST'ing Nginx health status to a remote service.

Nginx can use NJS to create HTTP requests based on access logs, using the format functionality to invoke NJS.  Some details about this can be found here: https://www.f5.com/company/blog/nginx/diagnostic-logging-nginx-javascript-module

However, for health check logs or any error logs, we don't have any formatting customization options.  THis means we have no way to invoke NJS to create an HTTP request based on error logs.

We can however, send error logs to syslog, and from syslog, we can send them via HTTP to some other services.  Both common syslog daemons: rsyslogd and syslog-ng support the ability to send HTTP requests based on log messages, this example shows how to configure rsyslogd to perform this action.

The key config elements on the Nginx side is to send error_log to syslog:
```error_log  syslog:server=127.0.0.1,facility=local7,tag=nginx notice;```
Note that you can configure teh facility, to help with filtering when using syslog daemon to generate the HTTP request.

## Nginx Config to send to syslog

Note this Nginx config also has a logPost location which will dump post payloads into files.

```
user  nginx;
worker_processes  auto;

error_log  /var/log/nginx/error.log notice;
error_log  syslog:server=127.0.0.1,facility=local7,tag=nginx notice;
pid        /var/run/nginx.pid;

load_module modules/ngx_http_js_module.so;

events {
    worker_connections  1024;
}


http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;

    js_import health_callback.js;


    log_format  main  '$remote_addr - $remote_user [$time_local] "$request" '
                      '$status $body_bytes_sent "$http_referer" '
                      '"$http_user_agent" "$http_x_forwarded_for"';

    access_log  /var/log/nginx/access.log  main;

    sendfile        on;
    #tcp_nopush     on;

    keepalive_timeout  65;

    #gzip  on;
    #include /etc/nginx/conf.d/*.conf;

    upstream app1_pool {
        zone app1_pool 64k;
        least_conn;
        server 10.12.3.252;
        server 192.0.0.1 backup;
    }

    match healthy_response {
        status 200-399;
        body ~ "status=ok";
    }

    server {
        listen 80;
        location / {
            proxy_pass http://app1_pool;
            health_check interval=10 fails=3 passes=2 uri=/status match=healthy_response mandatory persistent;
        }

    }

    server {
        listen 8080;
        root   /usr/share/nginx/html;
        location /logPost {
            limit_except POST              { deny all; }
            client_body_temp_path          /tmp/nginx;
            client_body_in_file_only       on;
            client_body_buffer_size        128K;
            client_max_body_size           50M;
            proxy_pass_request_headers     on;
            #proxy_set_header content-type "text/html";
            proxy_set_header               X-FILE $request_body_file;
            proxy_set_body                 $request_body_file;
            proxy_pass                     http://localhost:8080/;
            proxy_redirect                 off;
        }
    }


}
```

## rsyslogd config to send HTTP POST

For detailed config options see: https://www.rsyslog.com/doc/configuration/modules/omhttp.html

Note this uses the omhttp module, which you may have to build rsyslog yourself to use.

```
# include the omhttp module
module(load="omhttp")

# Produces JSON formatted payload
template(name="tpl_omhttp_json" type="list") {
    constant(value="{")   property(name="msg"           outname="message"   format="jsonfr")
    constant(value=",")   property(name="hostname"      outname="host"      format="jsonfr")
    constant(value=",")   property(name="timereported"  outname="timestamp" format="jsonfr" dateFormat="rfc3339")
    constant(value="}")
}

# action to send Nginx Health change messages via http
if $syslogfacility-text == 'local7' and $msg contains 'peer is' then {
    action(
        type="omhttp"
        server="127.0.0.1"
        serverport="8080"
        restpath="logPost"
        useHttps="off"
        skipverifyhost="on"
        allowunsignedcerts="on"
        template="tpl_omhttp_json"

        # This won't batch messages beyond 1.
        batch="on"
        batch.format="jsonarray"
        batch.maxsize="1"

        errorfile="/var/log/rsyslog/omhttp_errors.log"
    )
    # Also log to file:
    action(type="omfile" file="/var/log/rsyslog/peer_change.log")
}

# action to send Nginx Health messages via http
if $syslogfacility-text == 'local7' and $msg contains 'health check' then {
    action(
        type="omhttp"
        server="127.0.0.1"
        serverport="8080"
        restpath="logPost"
        useHttps="off"
        skipverifyhost="on"
        allowunsignedcerts="on"
        template="tpl_omhttp_json"

        # This will batch up to 10 messages.
        batch="on"
        batch.format="jsonarray"
        batch.maxsize="10"

        errorfile="/var/log/rsyslog/omhttp_errors.log"
    )
    # Also log to file:
    action(type="omfile" file="/var/log/rsyslog/health_check.log")
}
```


## Example output:
Example of the POST data:

Healthy:
```
[
  {
    "message": " 2024/06/10 16:34:09 [notice] 53849#53849: peer is healthy while checking body, health check \"healthy_response\" of peer 10.12.3.252:80 in upstream \"app1_pool\"",
    "host": "herm-nginx",
    "timestamp": "2024-06-10T16:34:09+00:00"
  }
]
```

Unhealthy:
```
[
  {
    "message": " 2024/06/10 16:53:00 [warn] 53849#53849: peer is unhealthy while connecting to upstream, health check \"healthy_response\" of peer 10.12.3.252:80 in upstream \"app1_pool\"",
    "host": "herm-nginx",
    "timestamp": "2024-06-10T16:53:00+00:00"
  }
]
```

Health Check Error:
```
[
  {
    "message": " 2024/06/10 16:52:50 [error] 53849#53849: connect() failed (111: Connection refused) while connecting to upstream, health check \"healthy_response\" of peer 10.12.3.252:80 in upstream \"app1_pool\"",
    "host": "herm-nginx",
    "timestamp": "2024-06-10T16:52:50+00:00"
  }
]
```


## Python syslog listener & add upstreams
Let's say you wanted to do some complex set of actions based on an nginx upstream going up or down.  You could have a python script (or any other preferred programming language) that listens for basic syslog messages, and then performs some action based on them.

In this case, we've got a simple udp listener, which will then try to deploy a new upstream node when it senses one is down.

```python
import signal
import socket
import socketserver
import re
import requests
import json


HOST, PORT = "127.0.0.1", 5514

NGINX_API_URI = "http://127.0.0.1:8888"

def addUpstreamMember(upstream):
    deployUpstream = requests.session()
    deployUpstream.post('https://example.com/blah/')
    print("deploying upstream with post request")

    # this would normally be whatever you get back from your API to deploy upstreams as it's IP.
    newUpstreamMember = "192.0.2.100:80"

    updateNginxUpstream = requests.session()
    addMember = {}
    addMember["server"] = newUpstreamMember
    addMember["weight"] = 1
    addMember["max_conns"] = 0
    addMember["max_fails"] = 2
    addMember["fail_timeout"] = "10"
    addMember["slow_start"] = "10s"
    addMember["backup"] = "false"
    addMember["down"] = "true"

    updateNginxUpstream.post('%s/api/9/http/upstreams/%s/servers' % (NGINX_API_URI, upstream), data=json.dumps(addMember) )


class SyslogUDPHandler(socketserver.BaseRequestHandler):
    def handle(self):
        data = bytes.decode(self.request[0].strip())
        if "peer is unhealthy" in str(data):
            regexMatch = re.match('.*of peer (\S+) in upstream (\S+)\s?.*', str(data))
            upstreamMember = regexMatch.group(1)
            upstreamName   = regexMatch.group(2)
            print("Unhealthy peer %s in in upstream %s" % (upstreamMember, upstreamName) )
            addUpstreamMember(upstreamName)


if __name__ == "__main__":
    print(f"Starting Syslog Server on {HOST}:{PORT}")
    try:
        server = socketserver.UDPServer((HOST,PORT), SyslogUDPHandler)
        server.serve_forever(poll_interval=0.5)
    except (IOError, SystemExit):
        raise
    except KeyboardInterrupt:
        print ("Crtl+C Pressed. Shutting down.")


    def signal_handler(sig, frame):
        server.shutdown()

    print('Stopping Syslog Server')
    server.server_close()
    exit(0)
```