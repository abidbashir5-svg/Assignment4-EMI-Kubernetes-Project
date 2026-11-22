#!/usr/bin/env bash
set -e
MINIKUBE_IP=$(minikube ip)
sudo sed -i '/[[:space:]]emi\.local$/d' /etc/hosts
echo "$MINIKUBE_IP emi.local" | sudo tee -a /etc/hosts
