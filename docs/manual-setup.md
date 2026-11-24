# Turn the local API on or off by hand

Normally the setup wizard offers to do this. Use these steps if it can't, or to turn the API off again. Replace `<gateway-ip>` and `<password>` with your values.

## Option A: in the gateway's web page

1. Open `https://<gateway-ip>` in a browser and accept the certificate warning.
   The gateway uses a self-signed certificate.
2. Log in with the password.
3. If you see an **Advanced** section: open it, accept the warning and turn on
   **WebSocket support**.

On firmware 10.12.2 the Advanced section **did not show up** for us. The page
showed only Timezone, Wi-Fi and Apple HomeKit, and `#/advanced` was blank. If
that happens to you, use option B. It uses the same calls as the page (and the setup wizard).

## Option B: from a terminal (works when the web page doesn't show it)

**Windows PowerShell** (5.1, the built-in one):

```powershell
[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}
[System.Net.ServicePointManager]::SecurityProtocol = 'Tls12'
$s = (Invoke-RestMethod 'https://<gateway-ip>/login' -Method Post -ContentType 'application/json' -Body '{"password":"<password>"}').session
Invoke-RestMethod 'https://<gateway-ip>/websocket_api' -Method Put -Headers @{'X-Session'=$s} -ContentType 'application/json' -Body '{"enable":true}'
```

No output means it worked. `-SkipCertificateCheck` only exists in PowerShell 7,
which is why the first line is there.

**Linux / macOS / Git Bash:**

```bash
S=$(curl -sk -X POST https://<gateway-ip>/login -H 'Content-Type: application/json' \
      -d '{"password":"<password>"}' | sed -E 's/.*"session":"([^"]+)".*/\1/')
curl -sk -X PUT https://<gateway-ip>/websocket_api -H "X-Session: $S" \
     -H 'Content-Type: application/json' -d '{"enable":true}'
```

## Check that it's on

```powershell
Test-NetConnection <gateway-ip> -Port 8443     # TcpTestSucceeded : True
```
```bash
nc -zv <gateway-ip> 8443
```

If Home Assistant is on another VLAN or subnet, allow it to reach **TCP 8443**
on the gateway.

## Turn it off again

The same steps with `{"enable":false}` in the last command.

```powershell
Invoke-RestMethod 'https://<gateway-ip>/websocket_api' -Method Put -Headers @{'X-Session'=$s} -ContentType 'application/json' -Body '{"enable":false}'
```
