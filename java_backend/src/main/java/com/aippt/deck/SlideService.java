package com.aippt.deck;

import java.util.List;
import java.util.UUID;

import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.spring.service.impl.ServiceImpl;

@Service
public class SlideService extends ServiceImpl<SlideMapper, Slide> {

    public List<Slide> listByProject(UUID projectId) {
        return this.lambdaQuery()
                .eq(Slide::getProjectId, projectId)
                .orderByAsc(Slide::getPosition)
                .list();
    }
}
