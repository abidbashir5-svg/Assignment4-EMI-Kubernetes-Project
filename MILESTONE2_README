# Assignment 4 — Milestone 2 deployment files

These files extend the Milestone 1 Flask application. Keep the existing `app.py` and `templates/` folder; replace the Dockerfile and add `.dockerignore` and `k8s/` from this package.

## 1. Overlay files into the Milestone 1 project

```bash
cd ~/Downloads
unzip -o milestone2_starter_kit.zip -d ~/projects/emi_milestone1
cd ~/projects/emi_milestone1
```

Check `app.py` and `templates/index.html` are still present.

## 2. Start Minikube and build the image inside Minikube

Stop the local Compose stack first if it is still running, so it does not consume RAM:

```bash
docker compose stop 2>/dev/null || true
minikube start
minikube image build -t emi-web:1.0 .
minikube image ls | grep emi-web
```

`minikube image build` avoids changing the shell's Docker context. If this command is unsupported by the installed Minikube version, use:

```bash
eval "$(minikube docker-env)"
docker build -t emi-web:1.0 .
```

## 3. Apply Kubernetes manifests

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/
```

The Mongo init Job waits for `mongo-0`, initializes replica set `rs0`, then waits until it sees one PRIMARY and two SECONDARY members. The EMI web pods remain unready until MongoDB responds to `/health`.

## 4. Watch deployment

```bash
kubectl get pods,pvc,svc -n emi -w
```

Wait until all three Mongo pods and all three `emi-web` pods show `Running` and `1/1` Ready, all three PVCs are `Bound`, and `mongo-init` is `Complete`. Press Ctrl+C to stop watching.

If pods are not ready, inspect only the relevant component:

```bash
kubectl get pods -n emi -o wide
kubectl describe pod -n emi <pod-name>
kubectl logs -n emi job/mongo-init
```

## 5. Verify replica set

```bash
kubectl exec -n emi mongo-0 -- mongosh --quiet --eval 'rs.status().members.map(m => ({name:m.name,state:m.stateStr}))'
kubectl logs -n emi job/mongo-init
```

Expected: `mongo-0.mongo:27017` PRIMARY and the other two members SECONDARY.

## 6. Open app locally through port-forward

In a terminal, run and keep this command active:

```bash
kubectl port-forward -n emi svc/emi-web 8080:80
```

Open `http://localhost:8080` in the browser. Perform a few calculations and confirm history updates.

## 7. Persistence test

Record PVC names and documents before deleting the secondary pod:

```bash
kubectl get pod mongo-1 -n emi -o wide
kubectl get pvc -n emi
kubectl exec -n emi mongo-0 -- mongosh --quiet --eval 'db.getSiblingDB("emidb").calculations.countDocuments({})'
```

Delete only `mongo-1`:

```bash
kubectl delete pod mongo-1 -n emi
kubectl get pods,pvc -n emi -w
```

After the pod is recreated and the replica set has recovered, run the count command again and confirm the count has not decreased. Confirm that the PVC named `mongo-data-mongo-1` remains bound and associated with the recreated pod.

## Submission evidence checklist

- [ ] Dockerfile and `.dockerignore`
- [ ] All YAML files under `k8s/`
- [ ] `kubectl get all,pvc -n emi -o wide`
- [ ] Replica-set members showing one PRIMARY and two SECONDARY
- [ ] `kubectl logs job/mongo-init -n emi`
- [ ] Application screenshot through port-forward, showing result and history
- [ ] Persistence test: `mongo-1` pod before/after, same PVC, document count before/after

## Notes

- The MongoDB URL is stored in a ConfigMap because the assignment does not configure MongoDB authentication credentials.
- The StatefulSet uses three 1 GiB PVCs from Minikube's `standard` StorageClass.
- No Ingress or HPA is created in this milestone; those are later assignment stages.
- Do not run the local Docker Compose MongoDB stack at the same time as the three-member Kubernetes MongoDB replica set on a memory-constrained machine.
- Do not use `docker compose down -v`; it deletes the local Compose data volume.
