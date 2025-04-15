SERVERS_JSON_FILE = aichat/agents/servers.json
SERVERS_JSON_TPL = aichat/agents/servers.json.tpl

.PHONY: run clean

run: $(SERVERS_JSON_FILE)
	op run --no-masking --env-file="./.env" -- uv run flet -d aichat/main.py ; $(MAKE) clean

$(SERVERS_JSON_FILE): $(SERVERS_JSON_TPL)
	op inject -i $(SERVERS_JSON_TPL) -o $(SERVERS_JSON_FILE)

clean:
	rm -f $(SERVERS_JSON_FILE)
