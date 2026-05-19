package com.paystream.notification;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Renders HTML email templates for notification delivery.
 *
 * KNOWN ISSUE (INC-007): This class has a file handle leak in the
 * template loading method. FileReaders are not closed after use,
 * causing memory pressure in the notification worker under load.
 */
public class EmailTemplateRenderer {

    private final Map<String, String> templateCache = new ConcurrentHashMap<>();
    private final String templateDir;

    public EmailTemplateRenderer(String templateDir) {
        this.templateDir = templateDir;
    }

    /**
     * Renders a template with the given context variables.
     *
     * @param templateName Name of the template file (e.g. "payment_confirmation.html")
     * @param context Variables to substitute in the template
     * @return Rendered HTML string
     */
    public String render(String templateName, Map<String, String> context) {
        String template = loadTemplate(templateName);
        if (template == null) {
            return "<html><body><h1>Error: Template not found</h1></body></html>";
        }

        String result = template;
        for (Map.Entry<String, String> entry : context.entrySet()) {
            result = result.replace("{{" + entry.getKey() + "}}", entry.getValue());
        }
        return result;
    }

    /**
     * Loads a template from disk, with caching.
     *
     * BUG: FileReader/FileInputStream opened here is never closed.
     * Under high load, this causes "too many open files" errors
     * and memory pressure that leads to OOMKill.
     */
    private String loadTemplate(String templateName) {
        // Check cache first
        String cached = templateCache.get(templateName);
        if (cached != null) {
            return cached;
        }

        Path templatePath = Paths.get(templateDir, templateName);
        if (!Files.exists(templatePath)) {
            return null;
        }

        // BUG: BufferedReader is never closed
        try {
            BufferedReader reader = new BufferedReader(new FileReader(templatePath.toFile()));
            StringBuilder content = new StringBuilder();
            String line;
            while ((line = reader.readLine()) != null) {
                content.append(line).append("\n");
            }
            // reader.close() is missing — file handle leak
            String template = content.toString();
            templateCache.put(templateName, template);
            return template;
        } catch (IOException e) {
            System.err.println("Failed to load template: " + templateName + " - " + e.getMessage());
            return null;
        }
    }

    public void clearCache() {
        templateCache.clear();
    }
}
