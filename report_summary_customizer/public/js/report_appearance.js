(() => {
	const SELECTORS = Object.freeze({
		reportPage: "#page-query-report",
		titleText: ".title-text",
		reportSummary: ".report-summary",
		summaryCard: ".summary-item",
		summaryLabel: ".summary-label",
		cardContent: ".rsa-card-content",
		cardIcon: ".rsa-summary-card-icon",
		cardDescription: ".rsa-summary-description",
		titleIcon: ".rsa-report-title-icon",
		menuItemParent: "li",
	});

	const CLASSES = Object.freeze({
		styledCard: "rsa-card-styled",
		cardContent: "rsa-card-content",
		cardIcon: "rsa-summary-card-icon",
		cardDescription: "rsa-summary-description",
		titleIcon: "rsa-report-title-icon",
		hiddenMenuItem: "rsa-menu-hidden",
		activePage: "rsa-report-appearance-active",
	});

	const GET_APPEARANCE_METHOD =
		"report_summary_customizer.api.report_appearance.get_report_appearance";
	const SET_APPEARANCE_METHOD =
		"report_summary_customizer.api.report_appearance.set_report_appearance";
	const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
	const SVG_ELEMENTS = new Set([
		"svg",
		"g",
		"path",
		"circle",
		"ellipse",
		"line",
		"polyline",
		"polygon",
		"rect",
	]);
	const SVG_ROOT_ATTRIBUTES = new Set([
		"width",
		"height",
		"viewBox",
		"fill",
		"stroke",
		"stroke-width",
		"stroke-linecap",
		"stroke-linejoin",
		"stroke-dasharray",
		"stroke-dashoffset",
		"fill-rule",
		"clip-rule",
		"opacity",
	]);
	const SVG_GEOMETRY_ATTRIBUTES = new Set([
		"d",
		"cx",
		"cy",
		"r",
		"rx",
		"ry",
		"x",
		"y",
		"x1",
		"y1",
		"x2",
		"y2",
		"width",
		"height",
		"points",
		"fill",
		"stroke",
		"stroke-width",
		"stroke-linecap",
		"stroke-linejoin",
		"stroke-dasharray",
		"stroke-dashoffset",
		"stroke-miterlimit",
		"fill-rule",
		"clip-rule",
		"opacity",
		"fill-opacity",
		"stroke-opacity",
		"transform",
	]);
	const SVG_GROUP_ATTRIBUTES = new Set([
		"fill",
		"stroke",
		"stroke-width",
		"stroke-linecap",
		"stroke-linejoin",
		"stroke-dasharray",
		"stroke-dashoffset",
		"stroke-miterlimit",
		"fill-rule",
		"clip-rule",
		"opacity",
		"fill-opacity",
		"stroke-opacity",
		"transform",
	]);
	const appearanceCache = new Map();
	const pendingAppearanceRequests = new Map();
	let routeGeneration = 0;

	if (frappe._rsaReportAppearanceInstalled) return;
	frappe._rsaReportAppearanceInstalled = true;

	function isCurrentReportRoute(reportName) {
		const route = frappe.get_route();
		return route[0] === "query-report" && route[1] === reportName;
	}

	function canSetAppearance() {
		const roles = frappe.user_roles || frappe.boot?.user?.roles || [];
		return (
			frappe.session?.user === "Administrator" ||
			roles.includes("Report Styler") ||
			roles.includes("System Manager")
		);
	}

	function clearAppearance(report) {
		if (!report) return;

		const title = report.page?.$title_area?.find(SELECTORS.titleText)?.get(0);
		if (title) {
			title.querySelectorAll(SELECTORS.titleIcon).forEach((icon) => icon.remove());
			title.style.removeProperty("color");
		}

		const summary = report.$summary?.get(0);
		if (!summary) return;

		summary.querySelectorAll(SELECTORS.summaryCard).forEach((card) => {
			card.querySelectorAll(SELECTORS.cardIcon).forEach((icon) => icon.remove());
			card.querySelectorAll(SELECTORS.cardDescription).forEach((description) =>
				description.remove()
			);
			card.classList.remove(CLASSES.styledCard);
			card.style.removeProperty("--rsa-card-border");

			const content = card.querySelector(SELECTORS.cardContent);
			if (content?.parentElement === card) {
				while (content.firstChild) {
					card.insertBefore(content.firstChild, content);
				}
				content.remove();
			}
		});
	}

	function makeIcon(iconName, className, size = "md") {
		if (typeof iconName !== "string") return null;

		const normalizedName = iconName.trim().replace(/^#?icon-/i, "");
		if (!/^[a-z0-9-]+$/i.test(normalizedName)) return null;

		const icon = $(frappe.utils.icon(normalizedName, size))[0];
		if (!icon || icon.tagName.toLowerCase() !== "svg") return null;
		icon.classList.add(className);
		return icon;
	}

	function makeSvgIcon(markup, className) {
		if (typeof markup !== "string" || !markup.trim() || markup.length > 50000) return null;
		if (/<!\s*(?:DOCTYPE|ENTITY)/i.test(markup)) return null;

		let source;
		try {
			source = new DOMParser().parseFromString(markup, "image/svg+xml").documentElement;
		} catch {
			return null;
		}
		if (
			!source ||
			source.localName?.toLowerCase() !== "svg" ||
			(source.namespaceURI && source.namespaceURI !== SVG_NAMESPACE)
		) {
			return null;
		}

		let nodeCount = 0;
		let hasGeometry = false;
		let invalid = false;
		const cloneTree = (element, isRoot = false, depth = 0) => {
			nodeCount += 1;
			const tagName = element.localName?.toLowerCase();
			if (
				nodeCount > 500 ||
				depth > 20 ||
				!SVG_ELEMENTS.has(tagName) ||
				(!isRoot && tagName === "svg") ||
				(element.namespaceURI && element.namespaceURI !== SVG_NAMESPACE)
			) {
				invalid = true;
				return null;
			}
			if (
				["path", "circle", "ellipse", "line", "polyline", "polygon", "rect"].includes(
					tagName
				)
			) {
				hasGeometry = true;
			}
			if (!isRoot && tagName !== "g" && element.children.length) {
				invalid = true;
				return null;
			}

			const clone = document.createElementNS(SVG_NAMESPACE, tagName);
			const allowedAttributes = isRoot
				? SVG_ROOT_ATTRIBUTES
				: tagName === "g"
				? SVG_GROUP_ATTRIBUTES
				: SVG_GEOMETRY_ATTRIBUTES;
			for (const attribute of Array.from(element.attributes || [])) {
				const name = attribute.localName;
				const value = attribute.value.trim();
				if (attribute.namespaceURI || !allowedAttributes.has(name)) continue;
				if (!value || value.length > 20000 || /url\s*\(|javascript:/i.test(value)) {
					invalid = true;
					return null;
				}
				clone.setAttribute(name, value);
			}
			for (const child of Array.from(element.childNodes || [])) {
				if (child.nodeType === Node.TEXT_NODE) {
					if (child.textContent.trim()) invalid = true;
					continue;
				}
				if (child.nodeType !== Node.ELEMENT_NODE) continue;
				const childClone = cloneTree(child, false, depth + 1);
				if (childClone) clone.appendChild(childClone);
			}
			return clone;
		};

		const icon = cloneTree(source, true);
		if (!icon || invalid || !hasGeometry) return null;
		icon.classList.add(className);
		return icon;
	}

	function ensureCardContent(card) {
		let content = card.querySelector(SELECTORS.cardContent);
		if (content?.parentElement === card) return content;

		content = document.createElement("div");
		content.className = CLASSES.cardContent;
		while (card.firstChild) {
			content.appendChild(card.firstChild);
		}
		card.appendChild(content);
		return content;
	}

	function setCardDescription(content, description) {
		let element = content.querySelector(SELECTORS.cardDescription);
		if (typeof description !== "string" || !description.trim()) {
			element?.remove();
			return;
		}

		if (!element) {
			element = document.createElement("div");
			element.className = CLASSES.cardDescription;
			content.appendChild(element);
		}
		element.textContent = description.trim();
	}

	function syncReportPageClass(reportName, active) {
		const page = document.querySelector(SELECTORS.reportPage);
		if (!page) return;

		page.classList.toggle(
			CLASSES.activePage,
			Boolean(active && isCurrentReportRoute(reportName))
		);
	}

	function applyAppearance(report, appearance) {
		clearAppearance(report);
		if (!report || report._rsaSummaryReportName !== report.report_name) {
			syncReportPageClass(report?.report_name, false);
			return;
		}
		if (!appearance?.configured) {
			syncReportPageClass(report.report_name, false);
			return;
		}

		const title = report.page?.$title_area?.find(SELECTORS.titleText)?.get(0);
		if (title) {
			if (isHexColor(appearance.color)) {
				title.style.setProperty("color", appearance.color);
			}

			const titleIcon =
				makeSvgIcon(appearance.icon_svg, CLASSES.titleIcon) ||
				makeIcon(appearance.icon, CLASSES.titleIcon, "md");
			if (titleIcon) title.prepend(titleIcon);
		}

		const summary = report.$summary?.get(0);
		if (!summary) return;

		const cardStyles = new Map(
			(appearance.cards || []).map((card) => [card.card_label, card])
		);
		summary.querySelectorAll(SELECTORS.summaryCard).forEach((card) => {
			const label = card.querySelector(SELECTORS.summaryLabel)?.textContent.trim();
			// Labels are matched as displayed, so translated labels remain language-specific.
			const style = cardStyles.get(label);
			if (
				!style ||
				(!style.icon && !style.icon_svg && !style.border_color && !style.description)
			)
				return;

			card.classList.add(CLASSES.styledCard);
			if (isHexColor(style.border_color)) {
				card.style.setProperty("--rsa-card-border", style.border_color);
			}

			const content = ensureCardContent(card);
			const cardIcon =
				makeSvgIcon(style.icon_svg, CLASSES.cardIcon) ||
				makeIcon(style.icon, CLASSES.cardIcon, "md");
			if (cardIcon) card.insertBefore(cardIcon, content);
			setCardDescription(content, style.description);
		});
		syncReportPageClass(report.report_name, true);
	}

	function isHexColor(value) {
		return typeof value === "string" && /^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(value);
	}

	function installSummaryObserver(report) {
		if (report._rsaSummaryObserverInstalled) return;

		const summary = report.$summary?.get(0);
		if (!summary) return;

		const observer = new MutationObserver(() => {
			if (
				report._rsaSummaryReportName === report.report_name &&
				isCurrentReportRoute(report.report_name)
			) {
				applyAppearance(report, appearanceCache.get(report.report_name) || {});
			}
		});
		observer.observe(summary, { childList: true });
		report._rsaSummaryObserver = observer;
		report._rsaSummaryObserverInstalled = true;
	}

	function installSummaryRenderer(report) {
		if (report._rsaReportAppearanceRendererInstalled) return;

		const originalRenderSummary = report.render_summary;
		if (typeof originalRenderSummary !== "function") return;

		report.render_summary = function (...args) {
			const result = originalRenderSummary.apply(this, args);
			if (isCurrentReportRoute(this.report_name)) {
				this._rsaSummaryReportName =
					Array.isArray(args[0]) && args[0].length ? this.report_name : null;
				if (this._rsaSummaryReportName) {
					addAppearanceMenuItem(this.page);
					installSummaryObserver(this);
				} else {
					setMenuItemVisibility(this.page, false);
					syncReportPageClass(this.report_name, false);
				}
				applyAppearance(this, appearanceCache.get(this.report_name) || {});
			}
			return result;
		};
		report._rsaReportAppearanceRendererInstalled = true;
	}

	function fetchAppearance(reportName) {
		if (appearanceCache.has(reportName)) {
			return Promise.resolve(appearanceCache.get(reportName));
		}
		if (pendingAppearanceRequests.has(reportName)) {
			return pendingAppearanceRequests.get(reportName);
		}

		const request = frappe
			.call({
				method: GET_APPEARANCE_METHOD,
				type: "GET",
				args: { report: reportName },
			})
			.then(
				(response) => {
					const appearance = response.message || {};
					appearanceCache.set(reportName, appearance);
					pendingAppearanceRequests.delete(reportName);
					return appearance;
				},
				(error) => {
					pendingAppearanceRequests.delete(reportName);
					console.warn("Could not load report appearance", error);
					return {};
				}
			);
		pendingAppearanceRequests.set(reportName, request);
		return request;
	}

	function setMenuItemVisibility(page, visible) {
		page?._rsaReportAppearanceMenuItem
			?.closest(SELECTORS.menuItemParent)
			.toggleClass(CLASSES.hiddenMenuItem, !visible);
	}

	function addAppearanceMenuItem(page) {
		if (!page || !canSetAppearance()) {
			setMenuItemVisibility(page, false);
			return;
		}

		const menuItem = page._rsaReportAppearanceMenuItem;
		if (!menuItem || !menuItem.closest(SELECTORS.menuItemParent).get(0)?.isConnected) {
			page._rsaReportAppearanceMenuItem = page.add_menu_item(
				__("Set Appearance"),
				() => openAppearanceDialog(),
				false,
				null,
				true
			);
		}
		setMenuItemVisibility(page, true);
	}

	function waitForReportPage(reportName, attempts = 60) {
		return new Promise((resolve) => {
			let attempt = 0;
			const poll = () => {
				if (!isCurrentReportRoute(reportName)) {
					resolve(null);
					return;
				}

				const report = frappe.query_report;
				const title = report?.page?.$title_area?.find(SELECTORS.titleText);
				const expectedTitle = (report?.page_title || __(reportName)).trim();
				const pageReady =
					report?.report_name === reportName &&
					report.report_doc &&
					report.page?.main?.length &&
					report.$summary?.length &&
					title?.length &&
					title.text().trim() === expectedTitle;

				if (pageReady) {
					resolve(report);
					return;
				}
				if (++attempt >= attempts) {
					resolve(null);
					return;
				}
				setTimeout(poll, 100);
			};
			poll();
		});
	}

	async function handleRouteChange() {
		const generation = ++routeGeneration;
		const route = frappe.get_route();
		const targetReportName = route[0] === "query-report" ? route[1] : null;
		const previousReport = frappe.query_report;
		clearAppearance(previousReport);
		if (previousReport && previousReport._rsaSummaryReportName !== targetReportName) {
			previousReport._rsaSummaryReportName = null;
			previousReport.$summary?.empty();
		}
		syncReportPageClass(targetReportName, false);
		setMenuItemVisibility(previousReport?.page, false);

		if (route[0] !== "query-report" || !route[1]) return;

		const reportName = route[1];
		const report = await waitForReportPage(reportName);
		if (!report || generation !== routeGeneration || !isCurrentReportRoute(reportName)) return;

		installSummaryRenderer(report);
		if (
			report._rsaSummaryReportName !== reportName &&
			readDisplayedCardLabels(report).length
		) {
			report._rsaSummaryReportName = reportName;
		}
		if (report._rsaSummaryReportName === reportName) {
			addAppearanceMenuItem(report.page);
			installSummaryObserver(report);
		} else {
			setMenuItemVisibility(report.page, false);
			syncReportPageClass(reportName, false);
		}

		const appearance = await fetchAppearance(reportName);
		if (
			generation === routeGeneration &&
			isCurrentReportRoute(reportName) &&
			frappe.query_report === report
		) {
			applyAppearance(report, appearance);
		}
	}

	function readDisplayedCardLabels(report) {
		const summary = report.$summary?.get(0);
		if (!summary) return [];

		return Array.from(summary.querySelectorAll(SELECTORS.summaryCard))
			.map((card) => card.querySelector(SELECTORS.summaryLabel)?.textContent.trim())
			.filter(Boolean)
			.map((label) => ({ label }));
	}

	function expandColorForControl(color) {
		if (typeof color !== "string") return "";
		const shortColor = color.match(/^#([0-9a-f]{3})$/i);
		return shortColor ? `#${[...shortColor[1]].map((char) => char + char).join("")}` : color;
	}

	function openAppearanceDialog() {
		// Resolve the active report at click time because Frappe reuses the query-report page.
		const report = frappe.query_report;
		const reportName = report?.report_name;
		if (
			!reportName ||
			!isCurrentReportRoute(reportName) ||
			report._rsaSummaryReportName !== reportName ||
			!canSetAppearance()
		) {
			return;
		}

		fetchAppearance(reportName).then((appearance) => {
			if (frappe.query_report !== report || !isCurrentReportRoute(reportName)) return;

			const displayedCards = readDisplayedCardLabels(report);
			const savedCards = new Map(
				(appearance.cards || []).map((card) => [card.card_label, card])
			);
			const fields = [
				{
					fieldtype: "Section Break",
					fieldname: "rsa_report_appearance_section",
					label: __("Report Appearance"),
				},
				{
					fieldtype: "Icon",
					fieldname: "report_icon",
					label: __("Report Icon"),
					default: appearance.icon || "",
				},
				{
					fieldtype: "Small Text",
					fieldname: "report_icon_svg",
					label: __("Custom SVG Icon"),
					description: __(
						"Paste the complete inline SVG markup copied from Lucide. It appears beside the report title."
					),
					default: appearance.icon_svg || "",
				},
				{ fieldtype: "Column Break", fieldname: "rsa_report_color_column" },
				{
					fieldtype: "Color",
					fieldname: "title_color",
					label: __("Title Color"),
					default: expandColorForControl(appearance.color),
				},
			];

			displayedCards.forEach((card, index) => {
				const saved = savedCards.get(card.label) || {};
				fields.push(
					{
						fieldtype: "Section Break",
						fieldname: `rsa_card_section_${index}`,
						label: card.label,
					},
					{
						fieldtype: "Small Text",
						fieldname: `rsa_card_description_${index}`,
						label: __("Description"),
						default: saved.description || "",
					},
					{
						fieldtype: "Icon",
						fieldname: `rsa_card_icon_${index}`,
						label: __("Icon"),
						default: saved.icon || "",
					},
					{
						fieldtype: "Small Text",
						fieldname: `rsa_card_icon_svg_${index}`,
						label: __("Custom SVG Icon"),
						description: __(
							"Paste the complete inline SVG markup copied from Lucide. It appears in this summary card."
						),
						default: saved.icon_svg || "",
					},
					{ fieldtype: "Column Break", fieldname: `rsa_card_color_column_${index}` },
					{
						fieldtype: "Color",
						fieldname: `rsa_card_border_${index}`,
						label: __("Border Color"),
						default: expandColorForControl(saved.border_color),
					}
				);
			});

			const dialog = new frappe.ui.Dialog({
				title: __("Set Appearance"),
				fields,
				primary_action_label: __("Save"),
				primary_action(values) {
					if (!isCurrentReportRoute(reportName)) return;

					const displayedCardLabels = new Set(displayedCards.map((card) => card.label));
					const cards = [
						...(appearance.cards || []).filter(
							(card) => !displayedCardLabels.has(card.card_label)
						),
						...displayedCards.map((card, index) => ({
							card_label: card.label,
							icon: values[`rsa_card_icon_${index}`] || "",
							icon_svg: values[`rsa_card_icon_svg_${index}`] || "",
							border_color: values[`rsa_card_border_${index}`] || "",
							description: values[`rsa_card_description_${index}`] || "",
						})),
					];

					frappe
						.call({
							method: SET_APPEARANCE_METHOD,
							type: "POST",
							args: {
								report: reportName,
								icon: values.report_icon || "",
								icon_svg: values.report_icon_svg || "",
								color: values.title_color || "",
								cards: JSON.stringify(cards),
							},
						})
						.then((response) => {
							const updatedAppearance = response.message || {};
							appearanceCache.set(reportName, updatedAppearance);
							const activeReport = frappe.query_report;
							if (
								activeReport?.report_name === reportName &&
								isCurrentReportRoute(reportName)
							) {
								applyAppearance(activeReport, updatedAppearance);
							}
							dialog.hide();
							frappe.show_alert({
								message: __("Report appearance saved"),
								indicator: "green",
							});
						});
				},
			});
			dialog.show();
		});
	}

	frappe.router.on("change", handleRouteChange);
	$(document).on("page-change.rsaReportAppearance", handleRouteChange);
	$(document).ready(handleRouteChange);
})();
