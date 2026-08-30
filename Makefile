PACKAGE := dock-panel
VERSION ?= 0.1.9
PREFIX ?= /usr
DESTDIR ?=
COCKPITDIR := $(DESTDIR)$(PREFIX)/share/cockpit/$(PACKAGE)
LIBEXECDIR := $(DESTDIR)$(PREFIX)/libexec/$(PACKAGE)
STATEDIR := /var/lib/dock-panel
FRONTEND := frontend
BACKEND := backend
DISTDIR := dist
DISTNAME := $(PACKAGE)-$(VERSION)

.PHONY: all build dist pack install install-files devel-install uninstall clean test watch

all: build

build:
	cd $(FRONTEND) && npm ci && npm run build

# 本机编译，生成可拷到服务器的 tar.gz（服务器无需 Node）
dist: build pack

pack:
	rm -rf $(DISTDIR)/$(DISTNAME)
	mkdir -p $(DISTDIR)/$(DISTNAME)/cockpit $(DISTDIR)/$(DISTNAME)/backend
	test -f $(FRONTEND)/dist/manifest.json
	cp -a $(FRONTEND)/dist/. $(DISTDIR)/$(DISTNAME)/cockpit/
	cp -a $(BACKEND)/cli.py $(DISTDIR)/$(DISTNAME)/backend/cli.py
	cp -a $(BACKEND)/src $(DISTDIR)/$(DISTNAME)/backend/src
	install -m 0755 install.sh $(DISTDIR)/$(DISTNAME)/install.sh
	tar -C $(DISTDIR) -czf $(DISTDIR)/$(DISTNAME).tar.gz $(DISTNAME)
	cp -a $(DISTDIR)/$(DISTNAME).tar.gz $(DISTDIR)/$(PACKAGE).tar.gz
	@echo
	@echo "发布包: $(DISTDIR)/$(DISTNAME).tar.gz"
	@echo "服务器安装: curl -fsSL https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh | sudo sh"

# 本机直接装到当前系统（会先编译）
install: build install-files

# 只拷文件，不编译。适用于: 已 make build / 已解压发布包后在源码树里安装
install-files:
	install -d $(COCKPITDIR) $(LIBEXECDIR) $(DESTDIR)$(STATEDIR)/certs $(DESTDIR)$(STATEDIR)/projects
	cp -a $(FRONTEND)/dist/. $(COCKPITDIR)/
	rm -rf $(LIBEXECDIR)/src
	install -m 0755 $(BACKEND)/cli.py $(LIBEXECDIR)/cli.py
	cp -a $(BACKEND)/src $(LIBEXECDIR)/src

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
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules $(DISTDIR)
	find $(BACKEND) -type d -name __pycache__ -exec rm -rf {} +
