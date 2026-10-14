#!/usr/bin/env bash
# Launch an EC2 instance for Klaudesk and print its address.
#
#   AWS_PROFILE=... AWS_REGION=eu-west-1 KEY_NAME=... SECURITY_GROUP=sg-... deploy/launch-ec2.sh
#   INSTANCE_TYPE=t3.small ... deploy/launch-ec2.sh       # no GPU: model on Groq or a remote Ollama
#
# GPU types (default g4dn.xlarge) use the AWS Deep Learning Base GPU AMI (Ubuntu 22.04: NVIDIA
# driver, Docker and the NVIDIA container toolkit) and need a "Running On-Demand G and VT
# instances" quota of >= 4. Other types use Ubuntu 24.04.
set -euo pipefail

: "${AWS_REGION:?set AWS_REGION}"
: "${KEY_NAME:?set KEY_NAME (an EC2 key pair in this region)}"
: "${SECURITY_GROUP:?set SECURITY_GROUP (allow 22 from you, 80/443 public)}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g4dn.xlarge}"
DISK_GB="${DISK_GB:-60}"
NAME="${NAME:-khelp}"

# GPU types get the Deep Learning AMI; anything else gets plain Ubuntu 24.04.
if [[ "$INSTANCE_TYPE" == g* || "$INSTANCE_TYPE" == p* ]]; then
  AMI_PARAM=/aws/service/deeplearning/ami/x86_64/base-oss-nvidia-driver-gpu-ubuntu-22.04/latest/ami-id
else
  AMI_PARAM=/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id
  DISK_GB="${DISK_GB_CPU:-20}"
fi
AMI=$(aws ssm get-parameter --name "$AMI_PARAM" --query Parameter.Value --output text)
echo "AMI: $AMI ($INSTANCE_TYPE, ${DISK_GB} GB)"

ID=$(aws ec2 run-instances \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" --key-name "$KEY_NAME" \
  --security-group-ids "$SECURITY_GROUP" \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=${DISK_GB},VolumeType=gp3,DeleteOnTermination=true}" \
  --metadata-options "HttpTokens=required" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}},{Key=Project,Value=khelp}]" \
  --query 'Instances[0].InstanceId' --output text)
echo "Instance: $ID (waiting for it to run)"
aws ec2 wait instance-running --instance-ids "$ID"
IP=$(aws ec2 describe-instances --instance-ids "$ID" --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "Public IP: $IP"
echo "Next: deploy/remote-deploy.sh ubuntu@$IP ~/.ssh/<key>.pem"
