.PHONY: local
local:
	k6 run ./local/script.js

.PHONY: distributed
distributed:
	cp ./local/script.js ./distributed/script.js
	kubectl delete -k ./distributed/
	kubectl apply -k ./distributed/
	rm ./distributed/script.js
