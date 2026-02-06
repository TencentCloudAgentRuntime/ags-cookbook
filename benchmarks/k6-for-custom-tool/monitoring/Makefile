.PHONY: install
install:
	kubectl apply -k .

.PHONY: uninstall
uninstall:
	kubectl delete -k .

.PHONY: port-forward
port-forward:
	@echo "Prometheus: http://localhost:9090"
	@echo "Grafana: http://localhost:3000 (admin/admin)"
	kubectl port-forward svc/prometheus 9090:9090 &
	kubectl port-forward svc/grafana 3000:3000

.PHONY: status
status:
	kubectl get pods -l 'app in (prometheus, grafana)'
