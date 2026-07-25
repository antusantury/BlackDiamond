/**
 * Modern Deal Progress Component
 * Interactive deal progress component with animations and a modern UI.
 */

class DealProgress {
    constructor(container, options = {}) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.options = {
            language: options.language || 'en',
            showAnimations: options.showAnimations !== false,
            showPercentage: options.showPercentage !== false,
            showTimeEstimates: options.showTimeEstimates !== false,
            compact: options.compact || false,
            ...options
        };
        
        this.deal = options.deal || {};
        this.stages = this.getDealStages();
        this.currentStage = this.getCurrentStage();
        this.progressPercentage = this.calculateProgress();
        
        this.init();
    }
    
    init() {
        this.ensureStyles();
        this.render();
        if (this.options.showAnimations) {
            this.animateIn();
        }
    }

    ensureStyles() {
        if (typeof document === 'undefined') return;
        if (document.getElementById('deal-progress-styles')) return;

        const style = document.createElement('style');
        style.id = 'deal-progress-styles';
        style.textContent = `
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700&display=swap');

.deal-progress {
    --dp-bg: rgba(15, 23, 42, 0.9);
    --dp-surface: rgba(17, 24, 39, 0.92);
    --dp-border: rgba(148, 163, 184, 0.2);
    --dp-text: #f8fafc;
    --dp-muted: #94a3b8;
    --dp-accent: #22c55e;
    --dp-info: #38bdf8;
    font-family: "Manrope", sans-serif;
    color: var(--dp-text);
    background: linear-gradient(140deg, rgba(15, 23, 42, 0.9), rgba(9, 12, 20, 0.95));
    border: 1px solid var(--dp-border);
    border-radius: 16px;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
}

.deal-progress--compact {
    padding: 18px;
}

.deal-progress__header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 16px;
}

.deal-progress__title {
    margin: 0;
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: -0.02em;
}

.deal-progress__percentage {
    min-width: 160px;
    text-align: right;
}

.deal-progress__percentage-value {
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--dp-muted);
}

.deal-progress__percentage-bar {
    background: rgba(148, 163, 184, 0.15);
    height: 6px;
    border-radius: 999px;
    overflow: hidden;
    margin-top: 8px;
}

.deal-progress__percentage-fill {
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, var(--dp-info), var(--dp-accent));
}

.deal-progress__timeline {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.deal-progress__stage {
    display: grid;
    grid-template-columns: 36px 1fr;
    gap: 12px;
    align-items: flex-start;
}

.deal-progress__stage-marker {
    position: relative;
}

.deal-progress__stage-icon {
    width: 28px;
    height: 28px;
    border-radius: 9px;
    border: 1px solid var(--dp-border);
    background: rgba(148, 163, 184, 0.1);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.75rem;
    font-weight: 700;
    color: var(--dp-muted);
}

.deal-progress__stage-step {
    font-size: 0.75rem;
    letter-spacing: 0.04em;
}

.deal-progress__connector {
    position: absolute;
    left: 13px;
    top: 30px;
    bottom: -12px;
    width: 2px;
    background: rgba(148, 163, 184, 0.2);
}

.deal-progress__connector--completed {
    background: rgba(34, 197, 94, 0.6);
}

.deal-progress__stage--completed .deal-progress__stage-icon {
    border-color: rgba(34, 197, 94, 0.5);
    background: rgba(34, 197, 94, 0.2);
    color: var(--dp-text);
}

.deal-progress__stage--active .deal-progress__stage-icon {
    border-color: rgba(56, 189, 248, 0.5);
    background: rgba(56, 189, 248, 0.2);
    color: var(--dp-text);
}

.deal-progress__stage-title {
    font-weight: 600;
    margin-bottom: 4px;
}

.deal-progress__stage-description {
    color: var(--dp-muted);
    font-size: 0.9rem;
    line-height: 1.4;
}

.deal-progress__stage-time {
    margin-top: 6px;
    font-size: 0.8rem;
    color: var(--dp-muted);
    display: inline-flex;
    gap: 6px;
    align-items: center;
}

.deal-progress__time-label {
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    font-size: 0.7rem;
    color: var(--dp-text);
}

.deal-progress__action {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 12px 14px;
    border: 1px solid var(--dp-border);
    border-radius: 12px;
    background: rgba(148, 163, 184, 0.08);
}

.deal-progress__action-text {
    font-size: 0.9rem;
    color: var(--dp-muted);
}

.deal-progress__status-indicator {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: rgba(148, 163, 184, 0.5);
}

.deal-progress__status-indicator--active,
.deal-progress__status-indicator--funded,
.deal-progress__status-indicator--delivery_pending,
.deal-progress__status-indicator--receipt_pending,
.deal-progress__status-indicator--funds_pending,
.deal-progress__status-indicator--completed {
    background: var(--dp-accent);
}

@media (max-width: 640px) {
    .deal-progress {
        padding: 18px;
    }
    .deal-progress__header {
        flex-direction: column;
        align-items: flex-start;
    }
    .deal-progress__percentage {
        text-align: left;
        width: 100%;
    }
}
`;
        document.head.appendChild(style);
    }

    getDealStages() {
        const stages = {
            en: [
                {
                    id: 'deal_created',
                    title: 'Deal Created',
                    description: 'Buyer created the deal',
                    color: '#10b981'
                },
                {
                    id: 'seller_joined',
                    title: 'Seller Joined',
                    description: 'Seller joined the deal',
                    color: '#3b82f6'
                },
                {
                    id: 'payment_received',
                    title: 'Payment Received',
                    description: 'Funds locked in escrow',
                    color: '#8b5cf6'
                },
                {
                    id: 'delivery_confirmed',
                    title: 'Delivery Confirmed',
                    description: 'Seller confirmed delivery',
                    color: '#f59e0b'
                },
                {
                    id: 'receipt_confirmed',
                    title: 'Receipt Confirmed',
                    description: 'Buyer confirmed receipt',
                    color: '#10b981'
                },
                {
                    id: 'funds_transferred',
                    title: 'Funds Transferred',
                    description: 'Funds transferred to seller',
                    color: '#10b981'
                }
            ],

            ua: [
                {
                    id: 'deal_created',
                    title: 'Угода створена',
                    description: 'Покупець створив угоду',
                    color: '#10b981'
                },
                {
                    id: 'seller_joined',
                    title: 'Продавець приєднався',
                    description: 'Продавець приєднався до угоди',
                    color: '#3b82f6'
                },
                {
                    id: 'payment_received',
                    title: 'Оплата отримана',
                    description: 'Кошти заблоковані в ескроу',
                    color: '#8b5cf6'
                },
                {
                    id: 'delivery_confirmed',
                    title: 'Доставка підтверджена',
                    description: 'Продавець підтвердив доставку',
                    color: '#f59e0b'
                },
                {
                    id: 'receipt_confirmed',
                    title: 'Отримання підтверджено',
                    description: 'Покупець підтвердив отримання',
                    color: '#10b981'
                },
                {
                    id: 'funds_transferred',
                    title: 'Кошти переведені',
                    description: 'Кошти переведені продавцю',
                    color: '#10b981'
                }
            ]
        };
        
        return stages[this.options.language] || stages.en;
    }
    
    getCurrentStage() {
        const status = this.deal.status || 'pending';
        const hasSeller = !!this.deal.seller_id;
        
        const stageMap = {
            'pending': 'deal_created',
            'active': hasSeller ? 'seller_joined' : 'deal_created',
            'funded': 'payment_received',
            'delivery_pending': 'payment_received',
            'receipt_pending': 'delivery_confirmed',
            'funds_pending': 'receipt_confirmed',
            'completed': 'funds_transferred',
            'cancelled': 'deal_created',
            'expired': 'deal_created'
        };
        
        return stageMap[status] || 'deal_created';
    }
    
    calculateProgress() {
        const stageIndex = this.stages.findIndex(stage => stage.id === this.currentStage);
        if (stageIndex === -1) return 0;
        
        // Completed deals show 100%
        if (this.deal.status === 'completed') return 100;
        
        // Cancelled/expired deals show 0%
        if (['cancelled', 'expired'].includes(this.deal.status)) return 0;
        
        // Otherwise, calculate progress by stages
        return Math.round(((stageIndex + 1) / this.stages.length) * 100);
    }
    
    isStageCompleted(stageId) {
        const currentIndex = this.stages.findIndex(stage => stage.id === this.currentStage);
        const stageIndex = this.stages.findIndex(stage => stage.id === stageId);
        
        if (this.deal.status === 'completed') return true;
        if (['cancelled', 'expired'].includes(this.deal.status)) return false;
        
        return stageIndex <= currentIndex;
    }
    
    isStageActive(stageId) {
        return stageId === this.currentStage && !['completed', 'cancelled', 'expired'].includes(this.deal.status);
    }
    
    getTimeEstimate(stageId) {
        const estimates = {
            en: {
                'deal_created': '0 min',
                'seller_joined': '5-15 min',
                'payment_received': '10-30 min',
                'delivery_confirmed': '1-24 hours',
                'receipt_confirmed': '5-15 min',
                'funds_transferred': 'Instant'
            },

            ua: {
                'deal_created': '0 хв',
                'seller_joined': '5-15 хв',
                'payment_received': '10-30 хв',
                'delivery_confirmed': '1-24 години',
                'receipt_confirmed': '5-15 хв',
                'funds_transferred': 'Миттєво'
            }
        };
        
        return estimates[this.options.language]?.[stageId] || '';
    }
    
    render() {
        const compactClass = this.options.compact ? 'deal-progress--compact' : '';
        const animationsClass = this.options.showAnimations ? 'deal-progress--animated' : '';
        
        this.container.innerHTML = `
            <div class="deal-progress ${compactClass} ${animationsClass}" data-deal-code="${this.deal.deal_code || ''}">
                <div class="deal-progress__header">
                    <h3 class="deal-progress__title">${this.getTitle()}</h3>
                    ${this.options.showPercentage ? `
                        <div class="deal-progress__percentage">
                            <span class="deal-progress__percentage-value">${this.progressPercentage}%</span>
                            <div class="deal-progress__percentage-bar">
                                <div class="deal-progress__percentage-fill" style="width: ${this.progressPercentage}%"></div>
                            </div>
                        </div>
                    ` : ''}
                </div>
                
                <div class="deal-progress__timeline">
                    ${this.stages.map((stage, index) => this.renderStage(stage, index)).join('')}
                </div>
                
                <div class="deal-progress__actions">
                    ${this.renderActions()}
                </div>
            </div>
        `;
    }
    
    getTitle() {
        const titles = {
            en: 'Deal Progress',
            ua: 'Прогрес угоди'
        };
        return titles[this.options.language] || titles.en;
    }
    
    renderStage(stage, index) {
        const isCompleted = this.isStageCompleted(stage.id);
        const isActive = this.isStageActive(stage.id);
        const timeEstimate = this.getTimeEstimate(stage.id);
        
        let stageClass = 'deal-progress__stage';
        if (isCompleted) stageClass += ' deal-progress__stage--completed';
        if (isActive) stageClass += ' deal-progress__stage--active';
        
        const connector = index < this.stages.length - 1 ? 
            `<div class="deal-progress__connector ${isCompleted ? 'deal-progress__connector--completed' : ''}"></div>` : '';
        
        const stepLabel = String(index + 1).padStart(2, '0');
        return `
            <div class="${stageClass}" data-stage="${stage.id}">
                <div class="deal-progress__stage-marker">
                    <div class="deal-progress__stage-icon">
                        <span class="deal-progress__stage-step">${stepLabel}</span>
                    </div>
                    ${connector}
                </div>
                <div class="deal-progress__stage-content">
                    <div class="deal-progress__stage-title">${stage.title}</div>
                    <div class="deal-progress__stage-description">${stage.description}</div>
                    ${this.options.showTimeEstimates && timeEstimate ? `
                        <div class="deal-progress__stage-time">
                            <span class="deal-progress__time-label">ETA</span>
                            <span class="deal-progress__time-text">${timeEstimate}</span>
                        </div>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    renderActions() {
        const status = this.deal.status;
        const hasSeller = !!this.deal.seller_id;
        
        const actions = {
            en: {
                'pending': 'Share deal code with seller',
                'active': hasSeller ? 'Waiting for payment' : 'Waiting for seller',
                'funded': 'Confirm delivery received',
                'delivery_pending': 'Confirm delivery',
                'receipt_pending': 'Confirm receipt',
                'funds_pending': 'Withdraw funds',
                'completed': 'Deal completed successfully',
                'cancelled': 'Deal was cancelled',
                'expired': 'Deal has expired'
            },

            ua: {
                'pending': 'Поділіться кодом угоди з продавцем',
                'active': hasSeller ? 'Очікування оплати' : 'Очікування продавця',
                'funded': 'Підтвердіть отримання доставки',
                'delivery_pending': 'Підтвердити доставку',
                'receipt_pending': 'Підтвердити отримання',
                'funds_pending': 'Вивести кошти',
                'completed': 'Угода успішно завершена',
                'cancelled': 'Угода була скасована',
                'expired': 'Угода застаріла'
            }
        };
        
        const actionText = actions[this.options.language]?.[status] || actions.en[status] || '';
        
        return `
            <div class="deal-progress__action">
                <div class="deal-progress__action-text">${actionText}</div>
                <div class="deal-progress__action-status">
                    <div class="deal-progress__status-indicator deal-progress__status-indicator--${status}"></div>
                </div>
            </div>
        `;
    }
    
    animateIn() {
        const stages = this.container.querySelectorAll('.deal-progress__stage');
        stages.forEach((stage, index) => {
            stage.style.opacity = '0';
            stage.style.transform = 'translateY(20px)';
            
            setTimeout(() => {
                stage.style.transition = 'opacity 0.5s ease, transform 0.5s ease';
                stage.style.opacity = '1';
                stage.style.transform = 'translateY(0)';
            }, index * 100);
        });
    }
    
    update(dealData) {
        this.deal = { ...this.deal, ...dealData };
        this.currentStage = this.getCurrentStage();
        this.progressPercentage = this.calculateProgress();
        
        // Анимированное обновление
        if (this.options.showAnimations) {
            this.container.classList.add('deal-progress--updating');
            setTimeout(() => {
                this.render();
                this.container.classList.remove('deal-progress--updating');
            }, 300);
        } else {
            this.render();
        }
    }
    
    destroy() {
        if (this.container) {
            this.container.innerHTML = '';
        }
    }
    
    // Public methods for external control
    getProgress() {
        return {
            percentage: this.progressPercentage,
            currentStage: this.currentStage,
            stages: this.stages,
            deal: this.deal
        };
    }
    
    goToStage(stageId) {
        const stageExists = this.stages.some(stage => stage.id === stageId);
        if (stageExists) {
            this.currentStage = stageId;
            this.progressPercentage = this.calculateProgress();
            this.render();
        }
    }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DealProgress;
}

// Глобальная регистрация
if (typeof window !== 'undefined') {
    window.DealProgress = DealProgress;
}
