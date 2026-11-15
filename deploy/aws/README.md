# Run the site on AWS

One Lightsail machine runs the same FastAPI server as on your computer. A Lightsail
distribution in front gives it an `https://….cloudfront.net` address.

```
browser ── https ──> distribution ── http ──> machine (port 80)
                                              /opt/fire/app   server/, web/, data/
```

Why Lightsail: the AWS account this was written for may use Lightsail and S3 in
`us-east-1` only. Its organisation blocks EC2, Lambda, ECS, App Runner and SSM.

Cost while it exists: 12 USD a month for the machine (2 GB memory, 60 GB disk) and
2.50 USD a month for the distribution. Delete it after the event.

## Steps

1. Build the data (see "Run" in the main README). `data/fire.duckdb` must exist;
   `data/events/` is sent too when it exists.

2. Sign in to AWS:

```bash
aws configure
```

3. Create everything and publish:

```bash
deploy/aws/create.sh
```

It prints the address of the machine (works at once) and the https address (ready in
about 10 minutes).

4. Publish a new version of the code or the data later:

```bash
deploy/aws/upload.sh
```

Only committed code is sent.

5. Remove everything:

```bash
deploy/aws/delete.sh
```

## Files

| File | What it does |
|---|---|
| `common.sh` | Names, region and machine size. Change them here. |
| `create.sh` | Key pair, machine, fixed address, ports, then `upload.sh`, then the https address. |
| `upload.sh` | Copies code, data and secrets to the machine over SSH and runs `server.sh` there. |
| `server.sh` | On the machine: installs Python packages and (re)starts the service. |
| `delete.sh` | Removes what `create.sh` made. |

## Secrets

`upload.sh` copies `FIRMS_MAP_KEY` and `EE_PROJECT` from your `.env` to
`/opt/fire/app/.env` on the machine (readable by the server only). Nothing secret is
stored in the repository or in the scripts.

Landsat pictures need Earth Engine. A server cannot use the browser sign-in, so set
`EE_SERVICE_ACCOUNT_KEY` in `.env` to the path of a service-account key file before
`upload.sh`. Without it those pictures answer "not available"; the rest works.

## Good to know

- **Old answers:** the https address keeps the page and the `/api` answers for a day.
  `upload.sh` empties it after each publish.
- **Port 80** of the machine is open to everyone, so the site can also be read over
  plain http at the machine's address. Port 22 is open for `upload.sh`.
- **Logs:** `ssh -i ~/.ssh/fire-map-lightsail.pem ubuntu@ADDRESS`, then
  `journalctl -u fire -n 50`.
- **Not yet run:** the scripts were checked for syntax and `upload.sh` was rehearsed
  with stand-ins for `ssh` and `aws`. Nothing has been created on AWS with them yet.
