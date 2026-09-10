package com.ai_mbse.magicdraw.bridge;

import com.nomagic.magicdraw.core.Application;
import com.nomagic.magicdraw.core.Project;
import com.nomagic.magicdraw.core.project.ProjectDescriptor;
import com.nomagic.magicdraw.core.project.ProjectDescriptorsFactory;
import com.nomagic.magicdraw.openapi.uml.ModelElementsManager;
import com.nomagic.magicdraw.openapi.uml.PresentationElementsManager;
import com.nomagic.magicdraw.openapi.uml.ReadOnlyElementException;
import com.nomagic.magicdraw.plugins.Plugin;
import com.nomagic.magicdraw.uml.DiagramTypeConstants;
import com.nomagic.magicdraw.uml.symbols.DiagramPresentationElement;
import com.nomagic.magicdraw.uml.symbols.PresentationElement;
import com.nomagic.magicdraw.uml.symbols.paths.PathElement;
import com.nomagic.magicdraw.uml.symbols.shapes.ShapeElement;
import com.nomagic.magicdraw.openapi.uml.SessionManager;
import com.nomagic.uml2.ext.magicdraw.activities.mdfundamentalactivities.Activity;
import com.nomagic.uml2.ext.magicdraw.classes.mddependencies.Dependency;
import com.nomagic.uml2.ext.magicdraw.classes.mdinterfaces.Interface;
import com.nomagic.uml2.ext.magicdraw.classes.mdkernel.Diagram;
import com.nomagic.uml2.ext.magicdraw.classes.mdkernel.Element;
import com.nomagic.uml2.ext.magicdraw.classes.mdkernel.NamedElement;
import com.nomagic.uml2.ext.magicdraw.classes.mdkernel.Package;
import com.nomagic.uml2.ext.magicdraw.mdusecases.Actor;
import com.nomagic.uml2.ext.magicdraw.mdusecases.UseCase;
import com.nomagic.uml2.impl.ElementsFactory;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import javax.swing.SwingUtilities;
import javax.swing.UIDefaults;
import javax.swing.UIManager;
import javax.swing.plaf.FontUIResource;
import java.awt.Component;
import java.awt.Font;
import java.awt.GraphicsEnvironment;
import java.awt.Point;
import java.awt.Rectangle;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.lang.reflect.Method;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicReference;

public class AiMbseBridgePlugin extends Plugin {
    private static final int PORT = 7010;
    private HttpServer server;
    private volatile Map<String, Object> lastImport = new LinkedHashMap<String, Object>();

    @Override
    public void init() {
        try {
            configureChineseUiFont();
            server = HttpServer.create(new InetSocketAddress("127.0.0.1", PORT), 0);
            server.createContext("/api/health", this::handleHealth);
            server.createContext("/api/models/import", this::handleImport);
            server.createContext("/api/models/current", this::handleCurrentModel);
            server.createContext("/api/project/save", this::handleSaveProject);
            server.setExecutor(Executors.newCachedThreadPool());
            server.start();
            log("AI MBSE MagicDraw Bridge listening at http://127.0.0.1:" + PORT + "/api");
        } catch (Exception ex) {
            log("AI MBSE MagicDraw Bridge failed to start: " + ex.getMessage());
        }
    }

    private void configureChineseUiFont() {
        try {
            String family = firstAvailableFontFamily(new String[]{
                    "Microsoft YaHei UI",
                    "Microsoft YaHei",
                    "SimSun",
                    "NSimSun",
                    "Dialog"
            });
            if (family.length() == 0) {
                return;
            }
            UIDefaults defaults = UIManager.getDefaults();
            Enumeration<Object> keys = defaults.keys();
            while (keys.hasMoreElements()) {
                Object key = keys.nextElement();
                Object value = defaults.get(key);
                if (value instanceof FontUIResource) {
                    Font base = (Font) value;
                    defaults.put(key, new FontUIResource(family, base.getStyle(), base.getSize()));
                }
            }
            Object frame = invokeNoArg(Application.getInstance(), new String[]{"getMainFrame", "getFrame"});
            if (frame instanceof Component) {
                SwingUtilities.updateComponentTreeUI((Component) frame);
            }
            log("AI MBSE bridge configured MagicDraw UI font for Chinese text: " + family);
        } catch (Exception ex) {
            log("AI MBSE bridge could not configure Chinese UI font: " + ex.getMessage());
        }
    }

    private String firstAvailableFontFamily(String[] preferredFamilies) {
        String[] available = GraphicsEnvironment.getLocalGraphicsEnvironment().getAvailableFontFamilyNames();
        for (String preferred : preferredFamilies) {
            for (String family : available) {
                if (preferred.equalsIgnoreCase(family)) {
                    return family;
                }
            }
        }
        return "";
    }

    @Override
    public boolean close() {
        if (server != null) {
            server.stop(0);
            server = null;
        }
        return true;
    }

    @Override
    public boolean isSupported() {
        return true;
    }

    private void handleHealth(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        Project project = currentProject();
        String body = "{"
                + "\"status\":\"ok\","
                + "\"bridge\":\"ai-mbse-magicdraw-bridge\","
                + "\"version\":\"0.3.3\","
                + "\"project_open\":" + (project != null) + ","
                + "\"project_name\":\"" + json(project == null ? "" : project.getName()) + "\","
                + "\"last_import\":" + toJson(lastImport)
                + "}";
        sendJson(exchange, 200, body);
    }

    private void handleImport(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        final String body = readBody(exchange.getRequestBody());
        try {
            @SuppressWarnings("unchecked")
            final Map<String, Object> payload = (Map<String, Object>) new JsonParser(body).parse();
            Map<String, Object> result = callOnUiThread(() -> importPayload(payload));
            sendJson(exchange, 200, toJson(result));
        } catch (Exception ex) {
            Map<String, Object> error = new LinkedHashMap<String, Object>();
            error.put("status", "error");
            error.put("message", ex.getMessage());
            sendJson(exchange, 500, toJson(error));
        }
    }

    private void handleSaveProject(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        final String body = readBody(exchange.getRequestBody());
        try {
            final Map<String, Object> options = parseObjectBody(body);
            Map<String, Object> result = callOnUiThread(() -> saveCurrentProject(options));
            sendJson(exchange, 200, toJson(result));
        } catch (Exception ex) {
            Map<String, Object> error = new LinkedHashMap<String, Object>();
            error.put("status", "error");
            error.put("message", ex.getMessage());
            sendJson(exchange, 500, toJson(error));
        }
    }

    private void handleCurrentModel(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            sendJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        try {
            Map<String, Object> result = callOnUiThread(() -> readCurrentModel());
            sendJson(exchange, 200, toJson(result));
        } catch (Exception ex) {
            Map<String, Object> error = new LinkedHashMap<String, Object>();
            error.put("status", "error");
            error.put("message", ex.getMessage());
            sendJson(exchange, 500, toJson(error));
        }
    }

    private Map<String, Object> importPayload(Map<String, Object> payload) throws Exception {
        Project project = currentProject();
        if (project == null) {
            project = Application.getInstance().getProjectsManager().createProject();
        }

        @SuppressWarnings("unchecked")
        List<Object> rawElements = (List<Object>) payload.get("elements");
        @SuppressWarnings("unchecked")
        List<Object> rawRelationships = (List<Object>) payload.get("relationships");
        if (rawElements == null) {
            rawElements = new ArrayList<Object>();
        }
        if (rawRelationships == null) {
            rawRelationships = new ArrayList<Object>();
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> diagramLayout = (Map<String, Object>) payload.get("diagram_layout");
        @SuppressWarnings("unchecked")
        List<Object> rawDiagramViews = (List<Object>) payload.get("diagram_views");
        if (rawDiagramViews == null) {
            rawDiagramViews = new ArrayList<Object>();
        }

        String packageName = stringValue(payload.get("root_package"), "AI_MBSE_Demo");
        Map<String, NamedElement> imported = new LinkedHashMap<String, NamedElement>();
        List<Object> elementResults = new ArrayList<Object>();
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        SessionManager sessionManager = SessionManager.getInstance();
        boolean sessionCreated = false;
        try {
            if (!sessionManager.isSessionCreated(project)) {
                sessionManager.createSession(project, "AI MBSE import");
                sessionCreated = true;
            }
            Package rootPackage = findOrCreatePackage(project, packageName);
            int created = 0;
            int reused = 0;
            for (Object raw : rawElements) {
                @SuppressWarnings("unchecked")
                Map<String, Object> elementData = (Map<String, Object>) raw;
                String localId = stringValue(elementData.get("local_id"), "");
                String displayName = displayName(elementData);
                Package elementPackage = findOrCreateNestedPackage(project, rootPackage, stringValue(elementData.get("package"), ""));
                NamedElement element = findElement(elementPackage, displayName);
                if (element == null && localId.length() > 0) {
                    element = findElementByPrefix(elementPackage, localId + " - ");
                }
                if (element == null && elementPackage != rootPackage) {
                    element = findElement(rootPackage, displayName);
                    if (element == null && localId.length() > 0) {
                        element = findElementByPrefix(rootPackage, localId + " - ");
                    }
                }
                if (element == null) {
                    element = createElement(project.getElementsFactory(), elementData);
                    element.setOwner(elementPackage);
                    created++;
                    elementResults.add(elementRecord(localId, element, "created"));
                } else {
                    reused++;
                    elementResults.add(elementRecord(localId, element, "reused"));
                }
                element.setName(displayName);
                imported.put(localId, element);
            }
            int relationshipCount = 0;
            int relationshipsReused = 0;
            List<Dependency> dependencies = new ArrayList<Dependency>();
            List<Object> relationshipResults = new ArrayList<Object>();
            for (Object raw : rawRelationships) {
                @SuppressWarnings("unchecked")
                Map<String, Object> relationshipData = (Map<String, Object>) raw;
                NamedElement source = imported.get(stringValue(relationshipData.get("source"), ""));
                NamedElement target = imported.get(stringValue(relationshipData.get("target"), ""));
                if (source == null || target == null) {
                    continue;
                }
                String relationshipName = stringValue(relationshipData.get("name"),
                        stringValue(relationshipData.get("type"), "AI_MBSE_Relationship"));
                Package relationshipPackage = findOrCreateNestedPackage(project, rootPackage, stringValue(relationshipData.get("package"), "06_Traceability"));
                NamedElement existingRelationship = findElement(relationshipPackage, relationshipName);
                Dependency dependency;
                String relationshipAction;
                if (existingRelationship instanceof Dependency) {
                    dependency = (Dependency) existingRelationship;
                    relationshipsReused++;
                    relationshipAction = "reused";
                } else {
                    dependency = project.getElementsFactory().createDependencyInstance();
                    dependency.setName(relationshipName);
                    dependency.setOwner(relationshipPackage);
                    relationshipCount++;
                    relationshipAction = "created";
                }
                if (!dependency.getClient().contains(source)) {
                    dependency.getClient().add(source);
                }
                if (!dependency.getSupplier().contains(target)) {
                    dependency.getSupplier().add(target);
                }
                relationshipResults.add(relationshipRecord(relationshipData, dependency, relationshipAction));
                dependencies.add(dependency);
            }
            String diagramName = stringValue(payload.get("diagram_name"), "AI_MBSE_Trace_View");
            if (diagramLayout != null) {
                diagramName = stringValue(diagramLayout.get("diagram_name"), diagramName);
            }
            DiagramPresentationElement diagram = createOrUpdateDiagram(project, rootPackage, diagramName, imported, dependencies, diagramLayout, "requirements");
            List<String> diagramNames = new ArrayList<String>();
            if (diagram != null) {
                diagramNames.add(diagramName);
            }
            for (Object rawView : rawDiagramViews) {
                if (!(rawView instanceof Map)) {
                    continue;
                }
                @SuppressWarnings("unchecked")
                Map<String, Object> view = (Map<String, Object>) rawView;
                @SuppressWarnings("unchecked")
                Map<String, Object> viewLayout = (Map<String, Object>) view.get("layout");
                if (viewLayout == null) {
                    continue;
                }
                String viewName = stringValue(view.get("name"), stringValue(viewLayout.get("diagram_name"), "AI_MBSE_Diagram_View"));
                String viewType = stringValue(view.get("diagram_type"), stringValue(viewLayout.get("diagram_type"), "class"));
                viewName = displayDiagramName(viewName, viewType);
                if (viewLayout.get("diagram_name") == null) {
                    viewLayout.put("diagram_name", viewName);
                }
                viewLayout.put("diagram_name", viewName);
                viewLayout.put("diagram_type", viewType);
                DiagramPresentationElement viewDiagram = createOrUpdateDiagram(project, rootPackage, viewName, imported, dependencies, viewLayout, viewType);
                if (viewDiagram != null) {
                    diagramNames.add(viewName);
                }
            }
            if (sessionCreated) {
                sessionManager.closeSession(project);
            }
            if (diagram != null) {
                diagram.open();
            }
            result.put("status", "imported");
            result.put("project", project.getName());
            result.put("root_package", packageName);
            result.put("elements_created", created);
            result.put("elements_reused", reused);
            result.put("relationships_created", relationshipCount);
            result.put("relationships_reused", relationshipsReused);
            result.put("diagram", diagramName);
            result.put("diagrams", diagramNames);
            result.put("diagram_views_imported", Integer.valueOf(Math.max(0, diagramNames.size() - 1)));
            result.put("diagram_layout_source", diagramLayout == null ? "bridge_fallback" : "payload.diagram_layout");
            result.put("elements", elementResults);
            result.put("relationships", relationshipResults);
            lastImport = result;
            log("AI MBSE import completed: " + result);
            return result;
        } catch (Exception ex) {
            if (sessionCreated && sessionManager.isSessionCreated(project)) {
                sessionManager.cancelSession(project);
            }
            throw ex;
        }
    }

    private Map<String, Object> saveCurrentProject(Map<String, Object> options) throws Exception {
        Project project = currentProject();
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        if (project == null) {
            result.put("status", "no_project");
            result.put("saved", Boolean.FALSE);
            result.put("message", "No MagicDraw project is open.");
            return result;
        }
        ProjectDescriptor descriptor = ProjectDescriptorsFactory.getDescriptorForProject(project);
        if (descriptor == null) {
            descriptor = project.getLoadedFrom();
        }
        boolean needsNewDescriptor = descriptor == null || project.getFile() == null;
        File targetFile = saveTargetFile(project, options, needsNewDescriptor);
        if (targetFile != null) {
            File parent = targetFile.getParentFile();
            if (parent != null && !parent.exists() && !parent.mkdirs()) {
                throw new IOException("Could not create MagicDraw save directory: " + parent.getAbsolutePath());
            }
            descriptor = ProjectDescriptorsFactory.createLocalProjectDescriptor(project, targetFile);
        } else if (descriptor == null) {
            descriptor = ProjectDescriptorsFactory.createLocalProjectDescriptor(project);
        }
        if (descriptor == null) {
            throw new IllegalStateException("No ProjectDescriptor is available for current MagicDraw project.");
        }

        boolean saved = Application.getInstance().getProjectsManager().saveProject(descriptor, true);
        result.put("status", saved ? "saved" : "save_rejected");
        result.put("saved", Boolean.valueOf(saved));
        result.put("project", project.getName());
        result.put("project_id", objectId(project));
        result.put("descriptor_uri", descriptorUri(descriptor));
        if (targetFile != null) {
            result.put("file", targetFile.getAbsolutePath());
        }
        if (!saved) {
            result.put("message", "MagicDraw did not confirm the save operation.");
        }
        return result;
    }

    private Map<String, Object> parseObjectBody(String body) {
        if (body == null || body.trim().length() == 0) {
            return new LinkedHashMap<String, Object>();
        }
        Object parsed = new JsonParser(body).parse();
        if (!(parsed instanceof Map)) {
            throw new IllegalArgumentException("Save request body must be a JSON object.");
        }
        @SuppressWarnings("unchecked")
        Map<String, Object> map = (Map<String, Object>) parsed;
        return map;
    }

    private File saveTargetFile(Project project, Map<String, Object> options, boolean needsNewDescriptor) {
        String projectPath = stringValue(options.get("project_path"), "");
        if (projectPath.length() > 0) {
            return withMdzipExtension(new File(projectPath));
        }
        if (!needsNewDescriptor) {
            return null;
        }
        String saveDir = stringValue(options.get("save_dir"), "");
        if (saveDir.length() == 0) {
            return null;
        }
        return withMdzipExtension(new File(saveDir, safeFilePart(project.getName()) + ".mdzip"));
    }

    private File withMdzipExtension(File file) {
        String path = file.getPath();
        if (path.toLowerCase().endsWith(".mdzip")) {
            return file;
        }
        return new File(path + ".mdzip");
    }

    private String safeFilePart(String value) {
        String cleaned = stringValue(value, "AI_MBSE_MagicDraw_Project")
                .replaceAll("[^0-9A-Za-z_\\-.\\u4e00-\\u9fff]+", "_")
                .replaceAll("^_+|_+$", "");
        return cleaned.length() == 0 ? "AI_MBSE_MagicDraw_Project" : cleaned;
    }

    private String safePackagePart(String value) {
        String cleaned = stringValue(value, "")
                .replaceAll("[^0-9A-Za-z_\\-.\\u4e00-\\u9fff]+", "_")
                .replaceAll("^_+|_+$", "");
        return cleaned;
    }

    private String descriptorUri(ProjectDescriptor descriptor) {
        return descriptor == null || descriptor.getURI() == null ? "" : String.valueOf(descriptor.getURI());
    }

    private Map<String, Object> readCurrentModel() {
        Project project = currentProject();
        Map<String, Object> result = new LinkedHashMap<String, Object>();
        if (project == null) {
            result.put("status", "no_project");
            result.put("project_open", Boolean.FALSE);
            result.put("elements", new ArrayList<Object>());
            result.put("relationships", new ArrayList<Object>());
            result.put("diagrams", new ArrayList<Object>());
            return result;
        }

        List<Object> elements = new ArrayList<Object>();
        List<Object> relationships = new ArrayList<Object>();
        Package primary = project.getPrimaryModel();
        if (primary != null) {
            collectModelState(primary, elements, relationships);
        }

        List<Object> diagrams = new ArrayList<Object>();
        for (DiagramPresentationElement diagram : project.getDiagrams()) {
            Map<String, Object> item = new LinkedHashMap<String, Object>();
            item.put("name", diagram.getName());
            item.put("id", objectId(diagram.getDiagram()));
            diagrams.add(item);
        }

        result.put("status", "ok");
        result.put("project_open", Boolean.TRUE);
        result.put("project", project.getName());
        result.put("project_id", objectId(project));
        result.put("elements", elements);
        result.put("relationships", relationships);
        result.put("diagrams", diagrams);
        result.put("element_count", Integer.valueOf(elements.size()));
        result.put("relationship_count", Integer.valueOf(relationships.size()));
        return result;
    }

    private void collectModelState(Element owner, List<Object> elements, List<Object> relationships) {
        if (owner == null) {
            return;
        }
        for (Element child : owner.getOwnedElement()) {
            if (child instanceof Dependency) {
                relationships.add(relationshipState((Dependency) child));
            } else if (child instanceof NamedElement) {
                elements.add(elementState((NamedElement) child));
            }
            collectModelState(child, elements, relationships);
        }
    }

    private Map<String, Object> elementRecord(String localId, NamedElement element, String action) {
        Map<String, Object> record = elementState(element);
        record.put("local_id", localId);
        record.put("action", action);
        return record;
    }

    private Map<String, Object> elementState(NamedElement element) {
        Map<String, Object> record = new LinkedHashMap<String, Object>();
        String name = safeName(element);
        record.put("local_id", localIdFromName(name));
        record.put("magicdraw_id", objectId(element));
        record.put("qualified_name", qualifiedName(element));
        record.put("name", name);
        record.put("type", semanticType(element));
        record.put("metaclass", element == null ? "" : element.getClass().getSimpleName());
        record.put("owner", elementOwnerName(element));
        return record;
    }

    private Map<String, Object> relationshipRecord(Map<String, Object> data, Dependency dependency, String action) {
        Map<String, Object> record = relationshipState(dependency);
        record.put("local_id", stringValue(data.get("local_id"), stringValue(data.get("name"), String.valueOf(record.get("local_id")))));
        record.put("source", data.get("source"));
        record.put("target", data.get("target"));
        record.put("action", action);
        return record;
    }

    private Map<String, Object> relationshipState(Dependency dependency) {
        Map<String, Object> record = new LinkedHashMap<String, Object>();
        String name = safeName(dependency);
        NamedElement source = firstNamedElement(dependency.getClient());
        NamedElement target = firstNamedElement(dependency.getSupplier());
        record.put("local_id", localIdFromName(name));
        record.put("magicdraw_id", objectId(dependency));
        record.put("qualified_name", qualifiedName(dependency));
        record.put("name", name);
        record.put("type", "Dependency");
        record.put("source", localIdFromName(safeName(source)));
        record.put("source_name", safeName(source));
        record.put("target", localIdFromName(safeName(target)));
        record.put("target_name", safeName(target));
        record.put("owner", elementOwnerName(dependency));
        return record;
    }

    private String localIdFromName(String name) {
        if (name == null) {
            return "";
        }
        int separator = name.indexOf(" - ");
        if (separator > 0) {
            return name.substring(0, separator);
        }
        if (name.matches("^[A-Za-z]+-\\d+.*")) {
            int space = name.indexOf(' ');
            return space > 0 ? name.substring(0, space) : name;
        }
        return "";
    }

    private String objectId(Object object) {
        Object value = invokeNoArg(object, new String[]{"getID", "getId"});
        return value == null ? "" : String.valueOf(value);
    }

    private String qualifiedName(NamedElement element) {
        Object value = invokeNoArg(element, new String[]{"getQualifiedName", "getHumanName"});
        return value == null ? safeName(element) : String.valueOf(value);
    }

    private String elementOwnerName(Element element) {
        if (element == null || element.getOwner() == null) {
            return "";
        }
        Element owner = element.getOwner();
        if (owner instanceof NamedElement) {
            return qualifiedName((NamedElement) owner);
        }
        return owner.getClass().getSimpleName();
    }

    private Object invokeNoArg(Object target, String[] names) {
        if (target == null) {
            return null;
        }
        for (String name : names) {
            try {
                Method method = target.getClass().getMethod(name);
                method.setAccessible(true);
                return method.invoke(target);
            } catch (Exception ignored) {
                // Try the next candidate.
            }
        }
        return null;
    }

    private Package findOrCreatePackage(Project project, String packageName) {
        Package primary = project.getPrimaryModel();
        NamedElement existing = findElement(primary, packageName);
        if (existing instanceof Package) {
            return (Package) existing;
        }
        Package pkg = project.getElementsFactory().createPackageInstance();
        pkg.setName(packageName);
        pkg.setOwner(primary);
        return pkg;
    }

    private Package findOrCreateNestedPackage(Project project, Package rootPackage, String packagePath) {
        if (rootPackage == null || packagePath == null || packagePath.trim().length() == 0) {
            return rootPackage;
        }
        Package current = rootPackage;
        String[] parts = packagePath.split("[/\\\\:]+");
        for (String rawPart : parts) {
            String part = safePackagePart(rawPart);
            if (part.length() == 0) {
                continue;
            }
            NamedElement existing = findElement(current, part);
            if (existing instanceof Package) {
                current = (Package) existing;
                continue;
            }
            Package child = project.getElementsFactory().createPackageInstance();
            child.setName(part);
            child.setOwner(current);
            current = child;
        }
        return current;
    }

    private NamedElement createElement(ElementsFactory factory, Map<String, Object> data) {
        String type = stringValue(data.get("type"), "Block");
        String name = displayName(data);
        NamedElement element;
        if ("Actor".equalsIgnoreCase(type)) {
            Actor actor = factory.createActorInstance();
            element = actor;
        } else if ("UseCase".equalsIgnoreCase(type)) {
            UseCase useCase = factory.createUseCaseInstance();
            element = useCase;
        } else if ("Interface".equalsIgnoreCase(type)) {
            Interface iface = factory.createInterfaceInstance();
            element = iface;
        } else if ("Activity".equalsIgnoreCase(type)) {
            Activity activity = factory.createActivityInstance();
            element = activity;
        } else {
            com.nomagic.uml2.ext.magicdraw.classes.mdkernel.Class clazz = factory.createClassInstance();
            element = clazz;
        }
        element.setName(name);
        return element;
    }

    private DiagramPresentationElement createOrUpdateDiagram(
            Project project,
            Package rootPackage,
            String diagramName,
            Map<String, NamedElement> imported,
            List<Dependency> dependencies,
            Map<String, Object> diagramLayout,
            String diagramType) throws ReadOnlyElementException {
        DiagramPresentationElement existing = findDiagram(project, diagramName);
        if (existing == null) {
            Diagram diagram = ModelElementsManager.getInstance().createDiagram(diagramTypeConstant(diagramType), rootPackage);
            diagram.setName(diagramName);
            existing = project.getDiagram(diagram);
        }
        if (existing == null) {
            return null;
        }

        PresentationElementsManager manager = PresentationElementsManager.getInstance();
        Map<NamedElement, PresentationElement> symbols = new LinkedHashMap<NamedElement, PresentationElement>();
        Map<String, Integer> rowByType = new LinkedHashMap<String, Integer>();
        Map<String, Rectangle> layoutBoundsById = layoutBoundsById(diagramLayout);
        Map<String, Integer> layoutOrderById = layoutOrderById(diagramLayout);
        Map<String, List<Point>> layoutEdgePointsById = layoutEdgePointsById(diagramLayout);
        boolean scopedToLayout = !layoutBoundsById.isEmpty();
        List<Map.Entry<String, NamedElement>> orderedElements = new ArrayList<Map.Entry<String, NamedElement>>(imported.entrySet());
        Collections.sort(orderedElements, new Comparator<Map.Entry<String, NamedElement>>() {
            @Override
            public int compare(Map.Entry<String, NamedElement> left, Map.Entry<String, NamedElement> right) {
                Integer leftLayoutOrder = layoutOrderById.get(left.getKey());
                Integer rightLayoutOrder = layoutOrderById.get(right.getKey());
                if (leftLayoutOrder != null && rightLayoutOrder != null) {
                    return leftLayoutOrder.compareTo(rightLayoutOrder);
                }
                if (leftLayoutOrder != null) {
                    return -1;
                }
                if (rightLayoutOrder != null) {
                    return 1;
                }
                int typeCompare = Integer.valueOf(typeOrder(left.getValue())).compareTo(Integer.valueOf(typeOrder(right.getValue())));
                if (typeCompare != 0) {
                    return typeCompare;
                }
                return safeName(left.getValue()).compareTo(safeName(right.getValue()));
            }
        });

        for (Map.Entry<String, NamedElement> entry : orderedElements) {
            String localId = entry.getKey();
            if (scopedToLayout && !layoutBoundsById.containsKey(localId)) {
                continue;
            }
            NamedElement element = entry.getValue();
            String typeKey = semanticType(element);
            int row = rowByType.containsKey(typeKey) ? rowByType.get(typeKey).intValue() : 0;
            rowByType.put(typeKey, Integer.valueOf(row + 1));
            PresentationElement symbol = firstSymbol(project, element, existing);
            if (symbol == null) {
                symbol = manager.createShapeElement(element, existing);
            }
            if (symbol instanceof ShapeElement) {
                Rectangle bounds = layoutBoundsById.containsKey(localId) ? layoutBoundsById.get(localId) : layoutBounds(typeKey, row);
                manager.reshapeShapeElement((ShapeElement) symbol, bounds);
            }
            symbols.put(element, symbol);
        }
        for (Dependency dependency : dependencies) {
            PresentationElement client = null;
            PresentationElement supplier = null;
            NamedElement clientElement = firstNamedElement(dependency.getClient());
            NamedElement supplierElement = firstNamedElement(dependency.getSupplier());
            if (clientElement != null) {
                client = symbols.get(clientElement);
            }
            if (supplierElement != null) {
                supplier = symbols.get(supplierElement);
            }
            if (client != null && supplier != null) {
                PresentationElement pathSymbol = firstSymbol(project, dependency, existing);
                try {
                    if (pathSymbol == null) {
                        pathSymbol = manager.createPathElement(dependency, client, supplier);
                    }
                    if (pathSymbol instanceof PathElement) {
                        applyPathLayout(manager, (PathElement) pathSymbol, layoutEdgePointsById.get(dependency.getName()));
                    }
                } catch (Exception ex) {
                    log("AI MBSE bridge could not draw relationship " + dependency.getName() + ": " + ex.getMessage());
                }
            }
        }
        return existing;
    }

    private void applyPathLayout(
            PresentationElementsManager manager,
            PathElement path,
            List<Point> points) throws ReadOnlyElementException {
        if (points == null || points.size() < 2) {
            return;
        }
        Point clientPoint = points.get(0);
        Point supplierPoint = points.get(points.size() - 1);
        List<Point> breakPoints = new ArrayList<Point>();
        for (int index = 1; index < points.size() - 1; index++) {
            breakPoints.add(points.get(index));
        }
        path.setRectilinear();
        manager.changePathPoints(path, clientPoint, supplierPoint, breakPoints);
    }

    private String diagramTypeConstant(String diagramType) {
        String normalized = stringValue(diagramType, "class").trim().toLowerCase().replace('-', '_').replace(' ', '_');
        if ("usecase".equals(normalized)) {
            normalized = "use_case";
        }
        String[] candidates;
        if ("use_case".equals(normalized)) {
            candidates = new String[]{"UML_USE_CASE_DIAGRAM", "USE_CASE_DIAGRAM"};
        } else if ("activity".equals(normalized)) {
            candidates = new String[]{"UML_CLASS_DIAGRAM"};
        } else if ("sequence".equals(normalized)) {
            candidates = new String[]{"UML_CLASS_DIAGRAM"};
        } else if ("state".equals(normalized) || "state_machine".equals(normalized)) {
            candidates = new String[]{"UML_CLASS_DIAGRAM"};
        } else if ("ibd".equals(normalized) || "internal_block".equals(normalized)) {
            candidates = new String[]{"UML_CLASS_DIAGRAM"};
        } else if ("requirements".equals(normalized) || "requirement".equals(normalized)) {
            candidates = new String[]{"SYSML_REQUIREMENTS_DIAGRAM", "REQUIREMENTS_DIAGRAM", "UML_CLASS_DIAGRAM"};
        } else {
            candidates = new String[]{"UML_CLASS_DIAGRAM"};
        }
        for (String candidate : candidates) {
            try {
                Object value = DiagramTypeConstants.class.getField(candidate).get(null);
                if (value != null) {
                    return String.valueOf(value);
                }
            } catch (Exception ignored) {
                // Try the next MagicDraw version-specific diagram constant.
            }
        }
        return DiagramTypeConstants.UML_CLASS_DIAGRAM;
    }

    private String displayDiagramName(String diagramName, String diagramType) {
        String normalized = stringValue(diagramType, "class").trim().toLowerCase().replace('-', '_').replace(' ', '_');
        if ("usecase".equals(normalized)) {
            normalized = "use_case";
        }
        if (
                "ibd".equals(normalized)
                        || "internal_block".equals(normalized)
                        || "activity".equals(normalized)
                        || "sequence".equals(normalized)
                        || "state".equals(normalized)
                        || "state_machine".equals(normalized)
        ) {
            return diagramName.contains("完整视图") ? diagramName : diagramName + "（完整视图）";
        }
        return diagramName;
    }

    private NamedElement firstNamedElement(Collection<NamedElement> elements) {
        if (elements == null || elements.isEmpty()) {
            return null;
        }
        return elements.iterator().next();
    }

    private DiagramPresentationElement findDiagram(Project project, String diagramName) {
        for (DiagramPresentationElement diagram : project.getDiagrams()) {
            if (diagramName.equals(diagram.getName())) {
                return diagram;
            }
        }
        return null;
    }

    private PresentationElement firstSymbol(Project project, Element element, DiagramPresentationElement diagram) {
        Collection<PresentationElement> symbols = project.getSymbolElementMap().getAllPresentationElements(element, diagram);
        return symbols.isEmpty() ? null : symbols.iterator().next();
    }

    private Map<String, Rectangle> layoutBoundsById(Map<String, Object> diagramLayout) {
        Map<String, Rectangle> bounds = new LinkedHashMap<String, Rectangle>();
        if (diagramLayout == null) {
            return bounds;
        }
        for (Object rawNode : layoutNodes(diagramLayout)) {
            if (!(rawNode instanceof Map)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> node = (Map<String, Object>) rawNode;
            String id = stringValue(node.get("id"), stringValue(node.get("element_id"), ""));
            if (id.length() == 0) {
                continue;
            }
            bounds.put(
                    id,
                    new Rectangle(
                            intValue(node.get("x"), 70),
                            intValue(node.get("y"), 80),
                            intValue(node.get("width"), 220),
                            intValue(node.get("height"), 72)));
        }
        return bounds;
    }

    private Map<String, Integer> layoutOrderById(Map<String, Object> diagramLayout) {
        Map<String, Integer> order = new LinkedHashMap<String, Integer>();
        if (diagramLayout == null) {
            return order;
        }
        int index = 0;
        for (Object rawNode : layoutNodes(diagramLayout)) {
            if (!(rawNode instanceof Map)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> node = (Map<String, Object>) rawNode;
            String id = stringValue(node.get("id"), stringValue(node.get("element_id"), ""));
            if (id.length() > 0) {
                order.put(id, Integer.valueOf(index));
            }
            index++;
        }
        return order;
    }

    private Map<String, List<Point>> layoutEdgePointsById(Map<String, Object> diagramLayout) {
        Map<String, List<Point>> edges = new LinkedHashMap<String, List<Point>>();
        if (diagramLayout == null) {
            return edges;
        }
        Object rawEdges = diagramLayout.get("edges");
        if (!(rawEdges instanceof List)) {
            return edges;
        }
        @SuppressWarnings("unchecked")
        List<Object> edgeItems = (List<Object>) rawEdges;
        for (Object rawEdge : edgeItems) {
            if (!(rawEdge instanceof Map)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> edge = (Map<String, Object>) rawEdge;
            String id = stringValue(edge.get("relationship_id"), stringValue(edge.get("id"), ""));
            if (id.length() == 0) {
                continue;
            }
            List<Point> points = layoutPoints(edge.get("points"));
            if (points.size() >= 2) {
                edges.put(id, points);
            }
        }
        return edges;
    }

    private List<Point> layoutPoints(Object rawPoints) {
        if (!(rawPoints instanceof List)) {
            return Collections.emptyList();
        }
        @SuppressWarnings("unchecked")
        List<Object> pointItems = (List<Object>) rawPoints;
        List<Point> points = new ArrayList<Point>();
        for (Object rawPoint : pointItems) {
            if (!(rawPoint instanceof Map)) {
                continue;
            }
            @SuppressWarnings("unchecked")
            Map<String, Object> point = (Map<String, Object>) rawPoint;
            points.add(new Point(intValue(point.get("x"), 0), intValue(point.get("y"), 0)));
        }
        return points;
    }

    private List<Object> layoutNodes(Map<String, Object> diagramLayout) {
        Object rawNodes = diagramLayout == null ? null : diagramLayout.get("nodes");
        if (rawNodes instanceof List) {
            @SuppressWarnings("unchecked")
            List<Object> nodes = (List<Object>) rawNodes;
            return nodes;
        }
        return Collections.emptyList();
    }

    private Rectangle layoutBounds(String typeKey, int row) {
        int column = columnFor(typeKey);
        int x = 70 + column * 260;
        int y = 80 + row * 125;
        return new Rectangle(x, y, 220, 72);
    }

    private int columnFor(String typeKey) {
        if ("Actor".equals(typeKey)) {
            return 0;
        }
        if ("Activity".equals(typeKey)) {
            return 1;
        }
        if ("Block".equals(typeKey)) {
            return 2;
        }
        if ("Requirement".equals(typeKey)) {
            return 3;
        }
        if ("UseCase".equals(typeKey)) {
            return 4;
        }
        if ("Interface".equals(typeKey)) {
            return 5;
        }
        if ("ConstraintBlock".equals(typeKey)) {
            return 6;
        }
        return 2;
    }

    private int typeOrder(NamedElement element) {
        return columnFor(semanticType(element));
    }

    private String semanticType(NamedElement element) {
        String name = safeName(element);
        if (name.startsWith("ACT-")) {
            return "Activity";
        }
        if (name.startsWith("ACTOR-") || name.startsWith("BHV-ACTOR-")) {
            return "Actor";
        }
        if (name.startsWith("BLK-")) {
            return "Block";
        }
        if (name.startsWith("REQ-")) {
            return "Requirement";
        }
        if (name.startsWith("UC-")) {
            return "UseCase";
        }
        if (name.startsWith("IF-")) {
            return "Interface";
        }
        if (name.startsWith("CON-")) {
            return "ConstraintBlock";
        }
        if (element instanceof Activity) {
            return "Activity";
        }
        if (element instanceof Actor) {
            return "Actor";
        }
        if (element instanceof UseCase) {
            return "UseCase";
        }
        if (element instanceof Interface) {
            return "Interface";
        }
        return "Block";
    }

    private String safeName(NamedElement element) {
        return element == null || element.getName() == null ? "" : element.getName();
    }

    private String displayName(Map<String, Object> data) {
        String localId = stringValue(data.get("local_id"), "");
        String name = stringValue(data.get("name"), localId.length() > 0 ? localId : "UnnamedElement");
        if (localId.length() == 0 || name.startsWith(localId + " - ")) {
            return name;
        }
        return localId + " - " + name;
    }

    private NamedElement findElement(Package owner, String name) {
        if (name == null || owner == null) {
            return null;
        }
        for (Element element : owner.getOwnedElement()) {
            if (element instanceof NamedElement && name.equals(((NamedElement) element).getName())) {
                return (NamedElement) element;
            }
        }
        return null;
    }

    private NamedElement findElementByPrefix(Package owner, String prefix) {
        if (prefix == null || owner == null) {
            return null;
        }
        for (Element element : owner.getOwnedElement()) {
            if (element instanceof NamedElement) {
                String name = ((NamedElement) element).getName();
                if (name != null && name.startsWith(prefix)) {
                    return (NamedElement) element;
                }
            }
        }
        return null;
    }

    private Project currentProject() {
        Project project = Application.getInstance().getProject();
        if (project == null) {
            project = Application.getInstance().getProjectsManager().getActiveProject();
        }
        return project;
    }

    private interface UiCallable<T> {
        T call() throws Exception;
    }

    private <T> T callOnUiThread(UiCallable<T> callable) throws Exception {
        if (SwingUtilities.isEventDispatchThread()) {
            return callable.call();
        }
        CountDownLatch latch = new CountDownLatch(1);
        AtomicReference<T> value = new AtomicReference<T>();
        AtomicReference<Exception> error = new AtomicReference<Exception>();
        SwingUtilities.invokeLater(() -> {
            try {
                value.set(callable.call());
            } catch (Exception ex) {
                error.set(ex);
            } finally {
                latch.countDown();
            }
        });
        latch.await();
        if (error.get() != null) {
            throw error.get();
        }
        return value.get();
    }

    private static String readBody(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        int read;
        while ((read = input.read(buffer)) != -1) {
            output.write(buffer, 0, read);
        }
        return new String(output.toByteArray(), StandardCharsets.UTF_8);
    }

    private static void sendJson(HttpExchange exchange, int code, String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(code, bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static String stringValue(Object value, String fallback) {
        if (value == null) {
            return fallback;
        }
        String text = String.valueOf(value);
        return text.isEmpty() ? fallback : text;
    }

    private static int intValue(Object value, int fallback) {
        if (value instanceof Number) {
            return ((Number) value).intValue();
        }
        if (value != null) {
            try {
                return Integer.parseInt(String.valueOf(value));
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    private static String toJson(Object value) {
        if (value == null) {
            return "null";
        }
        if (value instanceof String) {
            return "\"" + json((String) value) + "\"";
        }
        if (value instanceof Number || value instanceof Boolean) {
            return String.valueOf(value);
        }
        if (value instanceof Map) {
            StringBuilder builder = new StringBuilder("{");
            boolean first = true;
            for (Object entryObject : ((Map<?, ?>) value).entrySet()) {
                Map.Entry<?, ?> entry = (Map.Entry<?, ?>) entryObject;
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(toJson(String.valueOf(entry.getKey()))).append(':').append(toJson(entry.getValue()));
            }
            return builder.append('}').toString();
        }
        if (value instanceof Collection) {
            StringBuilder builder = new StringBuilder("[");
            boolean first = true;
            for (Object item : (Collection<?>) value) {
                if (!first) {
                    builder.append(',');
                }
                first = false;
                builder.append(toJson(item));
            }
            return builder.append(']').toString();
        }
        return "\"" + json(String.valueOf(value)) + "\"";
    }

    private static String json(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\r", "\\r")
                .replace("\n", "\\n");
    }

    private void log(String text) {
        System.out.println(text);
    }

    private static final class JsonParser {
        private final String text;
        private int position;

        JsonParser(String text) {
            this.text = text == null ? "" : text;
        }

        Object parse() {
            Object value = readValue();
            skipWhitespace();
            if (position != text.length()) {
                throw new IllegalArgumentException("Unexpected JSON content at " + position);
            }
            return value;
        }

        private Object readValue() {
            skipWhitespace();
            if (position >= text.length()) {
                throw new IllegalArgumentException("Unexpected end of JSON");
            }
            char ch = text.charAt(position);
            if (ch == '{') {
                return readObject();
            }
            if (ch == '[') {
                return readArray();
            }
            if (ch == '"') {
                return readString();
            }
            if (text.startsWith("true", position)) {
                position += 4;
                return Boolean.TRUE;
            }
            if (text.startsWith("false", position)) {
                position += 5;
                return Boolean.FALSE;
            }
            if (text.startsWith("null", position)) {
                position += 4;
                return null;
            }
            return readNumber();
        }

        private Map<String, Object> readObject() {
            Map<String, Object> map = new LinkedHashMap<String, Object>();
            position++;
            skipWhitespace();
            if (peek('}')) {
                position++;
                return map;
            }
            while (true) {
                String key = readString();
                skipWhitespace();
                expect(':');
                Object value = readValue();
                map.put(key, value);
                skipWhitespace();
                if (peek('}')) {
                    position++;
                    return map;
                }
                expect(',');
            }
        }

        private List<Object> readArray() {
            List<Object> list = new ArrayList<Object>();
            position++;
            skipWhitespace();
            if (peek(']')) {
                position++;
                return list;
            }
            while (true) {
                list.add(readValue());
                skipWhitespace();
                if (peek(']')) {
                    position++;
                    return list;
                }
                expect(',');
            }
        }

        private String readString() {
            expect('"');
            StringBuilder builder = new StringBuilder();
            while (position < text.length()) {
                char ch = text.charAt(position++);
                if (ch == '"') {
                    return builder.toString();
                }
                if (ch == '\\') {
                    if (position >= text.length()) {
                        throw new IllegalArgumentException("Bad JSON escape");
                    }
                    char escaped = text.charAt(position++);
                    if (escaped == '"' || escaped == '\\' || escaped == '/') {
                        builder.append(escaped);
                    } else if (escaped == 'b') {
                        builder.append('\b');
                    } else if (escaped == 'f') {
                        builder.append('\f');
                    } else if (escaped == 'n') {
                        builder.append('\n');
                    } else if (escaped == 'r') {
                        builder.append('\r');
                    } else if (escaped == 't') {
                        builder.append('\t');
                    } else if (escaped == 'u') {
                        String hex = text.substring(position, position + 4);
                        builder.append((char) Integer.parseInt(hex, 16));
                        position += 4;
                    } else {
                        throw new IllegalArgumentException("Bad JSON escape: " + escaped);
                    }
                } else {
                    builder.append(ch);
                }
            }
            throw new IllegalArgumentException("Unterminated JSON string");
        }

        private Number readNumber() {
            int start = position;
            while (position < text.length()) {
                char ch = text.charAt(position);
                if ((ch >= '0' && ch <= '9') || ch == '-' || ch == '+' || ch == '.' || ch == 'e' || ch == 'E') {
                    position++;
                } else {
                    break;
                }
            }
            String number = text.substring(start, position);
            if (number.indexOf('.') >= 0 || number.indexOf('e') >= 0 || number.indexOf('E') >= 0) {
                return Double.valueOf(number);
            }
            return Long.valueOf(number);
        }

        private void skipWhitespace() {
            while (position < text.length() && Character.isWhitespace(text.charAt(position))) {
                position++;
            }
        }

        private boolean peek(char expected) {
            return position < text.length() && text.charAt(position) == expected;
        }

        private void expect(char expected) {
            skipWhitespace();
            if (position >= text.length() || text.charAt(position) != expected) {
                throw new IllegalArgumentException("Expected '" + expected + "' at " + position);
            }
            position++;
        }
    }
}
