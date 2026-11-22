# Assignment 4 — Loan EMI Calculator, MongoDB and Minikube

Repository layout:
- `app/` — Flask application, templates and Python requirements.
- `k8s/` — namespace, MongoDB StatefulSet/Services/init Job, web ConfigMap/Deployment/Service, Ingress and HPA manifests.
- `scripts/` — load tests, self-healing tests, rolling update/rollback helper, fixed-replica experiment script and Graph 2 capture script.
- `results/` — raw `httperf` output, CSV measurements, CPU data, graph images, and HPA summaries.
- `docs/` — Milestone 2 deployment notes.

## Fresh Minikube deployment

Start Minikube and enable required addons:

```bash
minikube start
minikube addons enable ingress
minikube addons enable metrics-server
```

Build the application image in Minikube:

```bash
minikube image build -t emi-web:1.0 .
```

Apply all Kubernetes manifests in filename order:

```bash
kubectl apply -f k8s/
```

Wait for the namespace resources:

```bash
kubectl get pods,pvc,svc -n emi -w
```

For host-based Ingress testing, map `emi.local` to the Minikube IP in `/etc/hosts`:

```bash
echo "$(minikube ip) emi.local" | sudo tee -a /etc/hosts
```

Open `http://emi.local`.

Check the HPA:

```bash
kubectl get hpa -n emi
kubectl top pods -n emi
```

The HPA manifest targets 50% average CPU utilisation, with minimum 1 and maximum 5 replicas.

## Results and reporting

The `results/` directory preserves raw measurements and the three required graphs. High-load results include overload, HTTP errors and reduced achieved request rates; these are retained and explained in the evidence log. The Graph 2 profile has two successful sample rounds at three pods. The archived HPA time-series has 19/40 points; the final repeated HPA outcome is captured as aggregate terminal evidence separately. See `results/` and `../Evidence/Milestone4/` in the full submission package.

## Reproducibility caveat

The HPA workload script was executed directly in the user's Ubuntu VM and its final time-series CSV was not included in the supplied archive. A note in `scripts/HPA_Experiment_Script_Note.md` documents this rather than supplying invented code or measurements.
