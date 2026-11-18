const confirmation = document.querySelector('#demo-payment-confirm[data-auto-submit]');
if (confirmation) {
    confirmation.requestSubmit();
}

const paymentConfig = document.getElementById('demo-payment-config');
if (paymentConfig) {
    loadDemoCheckout();
}

async function loadDemoCheckout() {
    const config = JSON.parse(paymentConfig.textContent);
    const status = document.getElementById('demo-payment-status');
    const button = document.getElementById('demo-payment-open');

    try {
        const widgets = TossPayments(config.clientKey).widgets({customerKey: config.customerKey});
        await widgets.setAmount({currency: 'KRW', value: config.amount});
        await Promise.all([
            widgets.renderPaymentMethods({selector: '#demo-payment-methods', variantKey: 'DEFAULT'}),
            widgets.renderAgreement({selector: '#demo-payment-agreement', variantKey: 'AGREEMENT'}),
        ]);
        status.textContent = '';
        button.disabled = false;
        button.addEventListener('click', async () => {
            button.disabled = true;
            status.textContent = '正在打开 Toss 测试支付…';
            try {
                await widgets.requestPayment({
                    orderId: config.orderId,
                    orderName: config.orderName,
                    successUrl: config.successUrl,
                    failUrl: config.failUrl,
                });
            } catch (error) {
                if (['PAY_PROCESS_CANCELED', 'USER_CANCEL'].includes(error.code)) {
                    const failure = new URL(config.failUrl);
                    failure.searchParams.set('code', error.code);
                    window.location.assign(failure);
                    return;
                }
                status.textContent = '暂时无法打开测试支付，请确认支付方式和条款后重试。';
                button.disabled = false;
            }
        });
    } catch (error) {
        status.textContent = '无法加载 Toss 测试结账。请检查网络后刷新页面。';
    }
}
