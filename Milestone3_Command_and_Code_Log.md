# Assignment 4 — Milestone 3 Command and Code Log

All commands below are the commands used or provided during the milestone workflow. Run from `~/projects/emi_milestone1` unless stated otherwise. The Python scripts used for request tests are included as separate files in this folder.

## A. Ingress and host-based access

```bash
minikube addons enable ingress
kubectl get pods -n ingress-nginx
kubectl get ingressclass
```

Ingress manifest: `07-emi-ingress.yaml`

```bash
kubectl apply -f k8s/07-emi-ingress.yaml

MINIKUBE_IP=$(minikube ip)
sudo sed -i '/[[:space:]]emi\.local$/d' /etc/hosts
echo "$MINIKUBE_IP emi.local" | sudo tee -a /etc/hosts

kubectl get ingress -n emi
curl -I http://emi.local
```

Observed route: host `emi.local`, path `/`, backend Service `emi-web:80`.
Observed HTTP check: `HTTP/1.1 200 OK`.

## B. Browser verification

Open:
- `http://emi.local`

The supplied browser screenshots show the Loan EMI Calculator page and calculation history.

## C. Load balancing with three replicas

The 30-request program is provided as `load_test_3_replicas.py`.

Run:
```bash
python3 load_test_3_replicas.py
```

Observed result:
- `emi-web-...-fpr69`: 10 requests
- `emi-web-...-s4nzp`: 10 requests
- `emi-web-...-v6x6t`: 10 requests
- Successful: 30
- Failed: 0

## D. Scale manually from three to five replicas

```bash
kubectl scale deployment emi-web --replicas=5 -n emi
kubectl rollout status deployment/emi-web -n emi
kubectl get pods -n emi -l app=emi-web -o wide
```

The screenshot shows five pods `1/1 Running`.

Run the five-replica request test:
```bash
python3 load_test_5_replicas.py
```

Observed result:
- Five pods served 6 requests each.
- Successful: 30
- Failed: 0

## E. Web Deployment self-healing

The pod selection/deletion and watch commands used were:

```bash
POD=$(kubectl get pods -n emi -l app=emi-web \
  -o jsonpath='{.items[0].metadata.name}')

echo "Deleting web pod: $POD"
kubectl delete pod "$POD" -n emi
kubectl get pods -n emi -l app=emi-web -w
```

The deleted pod was `emi-web-6669b74798-6d7ng`; the Deployment created replacement pod `emi-web-6669b74798-vqxp2`, which became `1/1 Running`.

While this happened, run:
```bash
python3 web_self_healing_request_test_20.py
```

Observed result:
- Successful: 20
- Failed: 0

## F. MongoDB PRIMARY failure and re-election

Identify the current PRIMARY:
```bash
kubectl exec mongo-0 -n emi -- mongosh --quiet --eval 'rs.status().members.forEach(m => print(m.name + " : " + m.stateStr))'
```

At the time of the test, `mongo-1` was PRIMARY, while `mongo-0` and `mongo-2` were SECONDARY.

Delete only the PRIMARY pod and wait for its StatefulSet replacement:
```bash
kubectl delete pod mongo-1 -n emi
kubectl wait --for=condition=Ready pod/mongo-1 -n emi --timeout=180s
```

Check the replica-set roles again:
```bash
kubectl exec mongo-0 -n emi -- mongosh --quiet --eval 'rs.status().members.forEach(m => print(m.name + " : " + m.stateStr))'
```

Observed final election:
- `mongo-0`: PRIMARY
- `mongo-1`: SECONDARY
- `mongo-2`: SECONDARY

The browser screenshots show that a new EMI calculation was saved and appeared in history after failover.

## G. Rolling update to version 1.1

The visible page title was changed using:
```bash
python3 change_title_for_version_1_1.py
```

Build the image inside Minikube:
```bash
minikube image build -t emi-web:1.1 .
```

Start continuous requests in another terminal:
```bash
python3 rolling_update_continuous_request_loop.py
```

Update the Deployment:
```bash
kubectl set image deployment/emi-web emi-web=emi-web:1.1 -n emi
kubectl rollout status deployment/emi-web -n emi
kubectl get deployment emi-web -n emi -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Observed image during update: `emi-web:1.1`.

## H. Rollback to version 1.0

With the request loop still running:
```bash
kubectl rollout undo deployment/emi-web -n emi
kubectl rollout status deployment/emi-web -n emi
kubectl get deployment emi-web -n emi -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

Observed final image: `emi-web:1.0`.

After the rollback completed, stop the request loop using Ctrl+C.

Observed request-loop summary:
- Total requests: 282
- Successful: 282
- Failed: 0

Get rollout history:
```bash
kubectl rollout history deployment/emi-web -n emi
```

Observed revisions: 1, 3 and 4 (change-cause entries were `<none>` because no change-cause annotation was set).

## I. Observed outcome summary

| Test | Observed result |
|---|---|
| Ingress HTTP check | HTTP 200 OK |
| 3-replica load test | 30 successful, 0 failed; 10 per pod |
| 5-replica load test | 30 successful, 0 failed; 6 per pod |
| Web pod deletion | Replacement pod became Ready |
| Requests during web self-healing | 20 successful, 0 failed |
| MongoDB primary deletion | New PRIMARY elected |
| App after MongoDB failover | Calculation saved and history updated |
| Rolling update | `emi-web:1.1` rollout successful |
| Rollback | Restored `emi-web:1.0` |
| Requests during update/rollback | 282 successful, 0 failed |

## Note on interpretation

The request-loop screenshot shows 282 HTTP 200 responses and zero failed requests after the loop was stopped following the rolling update and rollback. The deployment update and rollback commands are recorded in their own screenshots. Do not describe a measured latency or request throughput value: none was recorded in the supplied evidence.

## Evidence note for MongoDB self-healing watch output

The MongoDB primary deletion/re-election is evidenced by the before/after `rs.status()` screenshots and the successful post-failover browser calculation. A dedicated screenshot of `kubectl get pods -n emi -w` during the MongoDB pod's termination/recreation was not included in the supplied screenshots. The web-pod watch output is present for the web self-healing test.
