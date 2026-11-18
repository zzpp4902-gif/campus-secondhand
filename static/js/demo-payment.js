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
        let requesting = false;

        function cancelCheckout(code = 'USER_CANCEL') {
            const failure = new URL(config.failUrl);
            failure.searchParams.set('code', code);
            window.location.assign(failure);
        }

        async function requestPayment(paymentWindow) {
            if (requesting) return;
            requesting = true;
            button.disabled = true;
            try {
                await widgets.requestPayment({
                    orderId: config.orderId,
                    orderName: config.orderName,
                    windowTarget: 'self',
                    successUrl: config.successUrl,
                    failUrl: config.failUrl,
                });
            } catch (error) {
                if (['PAY_PROCESS_CANCELED', 'USER_CANCEL'].includes(error.code)) {
                    cancelCheckout(error.code);
                    return;
                }
                if (paymentWindow) await paymentWindow.destroy();
                status.textContent = '暂时无法打开测试支付，请确认支付方式和条款后重试。';
                button.disabled = false;
                requesting = false;
            }
        }

        async function openTossWindow() {
            button.disabled = true;
            const paymentWindow = await widgets.renderPaymentWindow({
                orderName: config.orderName,
                variantKey: {paymentMethod: 'DEFAULT', agreement: 'AGREEMENT'},
            });
            paymentWindow.on('paymentRequest', () => requestPayment(paymentWindow));
            paymentWindow.on('cancel', () => cancelCheckout());
            status.textContent = '请在 Toss 测试窗口中选择支付方式。';
        }

        if (!window.matchMedia('(max-width: 480px)').matches) {
            try {
                await openTossWindow();
                button.addEventListener('click', async () => {
                    try {
                        await openTossWindow();
                    } catch (error) {
                        status.textContent = '无法打开 Toss 测试窗口，请刷新后重试。';
                        button.disabled = false;
                    }
                });
                return;
            } catch (error) {
                // Use the embedded checkout when the provider window is unavailable.
            }
        }
        await Promise.all([
            widgets.renderPaymentMethods({selector: '#demo-payment-methods', variantKey: 'DEFAULT'}),
            widgets.renderAgreement({selector: '#demo-payment-agreement', variantKey: 'AGREEMENT'}),
        ]);
        status.textContent = '请选择一种测试支付方式，然后继续到 Toss。';
        button.disabled = false;
        button.addEventListener('click', () => requestPayment());
    } catch (error) {
        status.textContent = '无法加载 Toss 测试结账。请检查网络后刷新页面。';
    }
}
