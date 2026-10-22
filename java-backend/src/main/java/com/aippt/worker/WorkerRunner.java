package com.aippt.worker;

import java.time.Duration;

import org.springframework.boot.CommandLineRunner;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

import com.aippt.shared.json.JsonMapperHolder;
import com.aippt.shared.redis.JobQueue;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;

@Slf4j
@Component
@Profile("worker")
@RequiredArgsConstructor
public class WorkerRunner implements CommandLineRunner {

    private final JobQueue queue;
    private final OutlineJobHandler outlines;
    private final DeckJobHandler decks;

    @Override
    public void run(String... args) {
        log.info("AI PPT worker started");
        while (!Thread.currentThread().isInterrupted()) {
            String raw = queue.blockingPop(Duration.ofSeconds(5));
            if (raw == null) {
                continue;
            }
            try {
                JobPayload job = JsonMapperHolder.MAPPER.readValue(raw, JobPayload.class);
                dispatch(job);
            } catch (JobRetryException ex) {
                retry(raw);
            } catch (Exception ex) {
                log.error("任务处理失败: {}", raw, ex);
            }
        }
    }

    private void dispatch(JobPayload job) {
        switch (job.name()) {
            case JobPayload.OUTLINE -> outlines.handle(job);
            case JobPayload.DECK -> decks.handle(job);
            default -> log.warn("未知任务类型 {}", job.name());
        }
    }

    private void retry(String raw) {
        try {
            JobPayload job = JsonMapperHolder.MAPPER.readValue(raw, JobPayload.class);
            Thread.sleep(3_000);
            queue.requeue(JsonMapperHolder.MAPPER.writeValueAsString(job.retry()));
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        } catch (Exception ex) {
            log.error("任务重试入队失败", ex);
        }
    }
}
