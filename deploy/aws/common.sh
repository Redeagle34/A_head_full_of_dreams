# Shared by the scripts in this folder: names, region and how to reach the machine.
#
# Change here: NAME, REGION, ZONE, BUNDLE (machine size), KEY_FILE.
# The account this was written for may use Lightsail and S3 in us-east-1 only; EC2,
# Lambda, ECS, App Runner and SSM are blocked by its organisation.
NAME=fire-map
REGION=us-east-1
ZONE=us-east-1a
BLUEPRINT=ubuntu_24_04
BUNDLE=small_3_0                # 2 GB memory, 2 CPUs, 60 GB disk, 12 USD a month
CDN_BUNDLE=small_1_0            # 50 GB of traffic a month, 2.50 USD a month
KEY_FILE="$HOME/.ssh/$NAME-lightsail.pem"
KNOWN_HOSTS="$HOME/.ssh/$NAME-lightsail.known_hosts"
export AWS_DEFAULT_REGION="$REGION" AWS_PAGER=""

machine_ip() {
  aws lightsail get-instance --instance-name "$NAME" --query instance.publicIpAddress --output text
}

# on_machine COMMAND...   run a command on the machine
on_machine() {
  ssh -i "$KEY_FILE" -o UserKnownHostsFile="$KNOWN_HOSTS" -o StrictHostKeyChecking=accept-new \
      -o ConnectTimeout=10 "ubuntu@$IP" "$@"
}
