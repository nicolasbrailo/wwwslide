
restart_svc:
	systemctl restart wwwslide
	journalctl --follow --unit wwwslide

run_local:
	python3 ./main.py

install_deps:
	pipenv install flask

install_service:
	sudo cp ./wwwslide.service /etc/systemd/system/
	sudo systemctl daemon-reload
	systemctl restart wwwslide

logs:
	journalctl --follow --unit wwwslide


