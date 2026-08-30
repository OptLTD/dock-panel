PACKAGE := dock-panel
PREFIX ?= /usr
DESTDIR ?=
COCKPITDIR := $(DESTDIR)$(PREFIX)/share/cockpit/$(PACKAGE)
LIBEXECDIR := $(DESTDIR)$(PREFIX)/libexec/$(PACKAGE)
STATEDIR := /var/lib/dock-panel
FRONTEND := frontend
BACKEND := backend

.PHONY: all build install devel-install uninstall clean

all: build

build:
	cd $(FRONTEND) && npm ci && npm run build

install: build
	install -d $(COCKPITDIR) $(LIBEXECDIR) $(DESTDIR)$(STATEDIR)/certs $(DESTDIR)$(STATEDIR)/projects
	cp -a $(FRONTEND)/dist/. $(COCKPITDIR)/
	cp -a $(BACKEND)/. $(LIBEXECDIR)/
	install -m 0755 $(BACKEND)/cli.py $(LIBEXECDIR)/cli.py

devel-install: build
	mkdir -p $(HOME)/.local/share/cockpit
	ln -sfn $(CURDIR)/$(FRONTEND)/dist $(HOME)/.local/share/cockpit/$(PACKAGE)
	sudo mkdir -p /var/lib/dock-panel/certs /var/lib/dock-panel/projects
	sudo ln -sfn $(CURDIR)/$(BACKEND) /usr/libexec/$(PACKAGE)
	@echo "已链接到 ~/.local/share/cockpit/$(PACKAGE)"
	@echo "请重新登录 Cockpit 或执行: systemctl restart cockpit"

.PHONY: test
test:
	cd $(BACKEND) && PYTHONPATH=. python3 -m unittest tests.test_backend

.PHONY: watch
watch:
	cd $(FRONTEND) && npm run build -- --watch

uninstall:
	rm -rf $(COCKPITDIR) $(LIBEXECDIR)

clean:
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules
	find $(BACKEND) -type d -name __pycache__ -exec rm -rf {} +
