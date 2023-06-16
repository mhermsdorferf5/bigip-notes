# This iRule will send the customer a 'warning' page that the site is moving,
# That response includes a cookie, and a 10 second refresh delay.
# The Refresh takes them back to the originally requested URI.
# The cookies lifetime is configurable so that we can we can control how often
# we present the warning page to them.

when CLIENT_ACCEPTED { 
    # User Configurable variables:

    # Cookie Name, A cookie is used to decide if we need to respond with the warning page & refresh:
    set cookieName "mesgDelay"

    # Cookie Age in seconds, this controls how often a user sees the warning page:
    set cookieAge  "86400"

    # Warning page content:
    set httpContent {<html>
    <head><title>This site is going away, Update your bookmarks!</title></head>
    <body>
        <center>
        <h1>This site is going away, please update your bookmarks</h2>
        <h2>New Site is found at <a href="http://newsite.example.com/">http://newsite.example.com/</a>!</h2>
        <div>This page will reload in <span id="cnt" style="color:red;">10</span> Seconds</div>
        </center>
     
        <script>
            var counter = 10;
        
            // The countdown method.
            window.setInterval(function () {
                counter--;
                if (counter >= 0) {
                    var span;
                    span = document.getElementById("cnt");
                    span.innerHTML = counter;
                }
                if (counter === 0) {
                    clearInterval(counter);
                }
        
            }, 1000);
        
            window.setInterval('refresh()', 10000);
        
            // Refresh or reload page.
            function refresh() {
               window  .location.reload();
           }
        </script>
    </body>
    </html>}

}
when HTTP_REQUEST {
    if { ! [HTTP::cookie exists ${cookieName}] } {
        set cookie "${cookieName}=[HTTP::host][HTTP::uri]; domain=[HTTP::host]; Max-Age=${cookieAge}; HttpOnly; Secure"
        HTTP::respond 200 content $httpContent Set-Cookie $cookie
    }
}