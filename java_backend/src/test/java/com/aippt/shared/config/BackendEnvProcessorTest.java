package com.aippt.shared.config;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

class BackendEnvProcessorTest {

    @Test
    void parseReadsKeyValueAndIgnoresComments(@TempDir Path dir) throws Exception {
        Path file = dir.resolve(".env");
        Files.writeString(file, """
                # comment
                LLM_API_KEY=sk-from-python
                export IMAGE_PROVIDER=bailian
                EMPTY=
                """);
        Map<String, Object> values = BackendEnvProcessor.parse(file);
        assertEquals("sk-from-python", values.get("LLM_API_KEY"));
        assertEquals("bailian", values.get("IMAGE_PROVIDER"));
        assertEquals("", values.get("EMPTY"));
    }

    @Test
    void blankJavaValueDoesNotOverridePython() {
        Map<String, Object> merged = BackendEnvProcessor.merge(
                Map.of("LLM_API_KEY", "sk-from-python", "IMAGE_PROVIDER", "bailian"),
                Map.of("LLM_API_KEY", "", "IMAGE_PROVIDER", "openai")
        );
        assertEquals("sk-from-python", merged.get("LLM_API_KEY"));
        assertEquals("openai", merged.get("IMAGE_PROVIDER"));
    }

    @Test
    void missingOrBlankFillsOnlyEmptyKeys() {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new MapPropertySource("existing", Map.of(
                "LLM_API_KEY", "",
                "JWT_SECRET", "keep-me"
        )));
        Map<String, Object> fill = BackendEnvProcessor.missingOrBlank(environment, Map.of(
                "LLM_API_KEY", "sk-from-python",
                "JWT_SECRET", "python-secret",
                "IMAGE_API_KEY", "img-key"
        ));
        assertEquals("sk-from-python", fill.get("LLM_API_KEY"));
        assertEquals("img-key", fill.get("IMAGE_API_KEY"));
        assertFalse(fill.containsKey("JWT_SECRET"));
        assertTrue(fill.size() == 2);
    }
}
