// 대시보드 JavaScript

let currentCountry = 'KOR';
let toastTimeout = null;

// 숫자 포맷팅
function formatNumber(num, decimals = 0) {
    if (num === null || num === undefined || isNaN(num)) return '-';
    return new Intl.NumberFormat('ko-KR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    }).format(num);
}

// 통화 포맷팅
function formatCurrency(num, country = 'KOR') {
    if (num === null || num === undefined || isNaN(num)) return '-';
    const currency = country === 'KOR' ? 'KRW' : 'USD';
    return new Intl.NumberFormat('ko-KR', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 0
    }).format(num);
}

// 날짜 포맷팅
function formatDate(dateString) {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('ko-KR', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    }).format(date);
}

// 국가 전환
function switchCountry(country) {
    currentCountry = country;

    // 탭 버튼 활성화 상태 변경
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
        if (btn.dataset.country === country) {
            btn.classList.add('active');
        }
    });

    loadDashboard(country);
}

// 대시보드 데이터 로드
async function loadDashboard(country) {
    try {
        await Promise.all([
            loadAccountInfo(country),
            loadHoldings(country)
        ]);
    } catch (error) {
        console.error('대시보드 로드 실패:', error);
    }
}

// 계좌 정보 로드
async function loadAccountInfo(country) {
    try {
        const response = await fetch(`/api/dashboard/account?country=${country}`);
        if (!response.ok) throw new Error('계좌 정보 로드 실패');

        const data = await response.json();

        document.getElementById('total-asset').textContent = formatCurrency(data.total_asset, country);
        document.getElementById('cash').textContent = formatCurrency(data.cash, country);
        document.getElementById('stock-value').textContent = formatCurrency(data.stock_value, country);
        document.getElementById('profit-loss').textContent = formatCurrency(data.profit_loss, country);

        const profitLossRate = data.profit_loss_rate;
        const rateElement = document.getElementById('profit-loss-rate');
        rateElement.textContent = `${profitLossRate >= 0 ? '+' : ''}${formatNumber(profitLossRate, 2)}%`;
        rateElement.className = `card-change ${profitLossRate >= 0 ? 'positive' : 'negative'}`;

        // 총 자산 변동률 (임시)
        const changeElement = document.getElementById('total-asset-change');
        changeElement.textContent = `전일 대비 ${profitLossRate >= 0 ? '+' : ''}${formatNumber(profitLossRate, 2)}%`;
        changeElement.className = `card-change ${profitLossRate >= 0 ? 'positive' : 'negative'}`;

    } catch (error) {
        console.error('계좌 정보 로드 실패:', error);
        showError('계좌 정보를 불러올 수 없습니다.');
    }
}

// 보유 종목 로드
async function loadHoldings(country) {
    try {
        const response = await fetch(`/api/dashboard/holdings?country=${country}`);
        if (!response.ok) throw new Error('보유 종목 로드 실패');

        const holdings = await response.json();
        const tbody = document.getElementById('holdings-table');

        if (holdings.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" class="text-center text-gray-500 py-8">
                        보유 중인 종목이 없습니다.
                    </td>
                </tr>
            `;
            document.getElementById('holdings-count').textContent = '0개';
            return;
        }

        tbody.innerHTML = holdings.map(stock => {
            const isProfit = stock.profit_loss >= 0;
            return `
                <tr>
                    <td class="font-medium">${stock.symbol}</td>
                    <td>${stock.name}</td>
                    <td class="text-right">${formatNumber(stock.quantity)}주</td>
                    <td class="text-right">${formatCurrency(stock.avg_price, country)}</td>
                    <td class="text-right font-medium">${formatCurrency(stock.current_price, country)}</td>
                    <td class="text-right ${isProfit ? 'positive' : 'negative'} font-medium">
                        ${isProfit ? '+' : ''}${formatCurrency(stock.profit_loss, country)}
                    </td>
                    <td class="text-right">
                        <span class="badge ${isProfit ? 'badge-success' : 'badge-danger'}">
                            ${isProfit ? '+' : ''}${formatNumber(stock.profit_loss_rate, 2)}%
                        </span>
                    </td>
                </tr>
            `;
        }).join('');

        document.getElementById('holdings-count').textContent = `${holdings.length}개`;

    } catch (error) {
        console.error('보유 종목 로드 실패:', error);
        showError('보유 종목을 불러올 수 없습니다.');
    }
}

// 시스템 상태 로드
async function loadSystemStatus() {
    try {
        const response = await fetch('/api/dashboard/status');
        if (!response.ok) throw new Error('시스템 상태 로드 실패');

        const status = await response.json();

        document.getElementById('scheduler-status').textContent =
            status.scheduler_running ? '실행 중' : '중지됨';
        document.getElementById('scheduler-status').className =
            `badge ${status.scheduler_running ? 'badge-success' : 'badge-danger'}`;

        document.getElementById('last-update').textContent = formatDate(status.last_update);
        document.getElementById('total-stocks').textContent = formatNumber(status.total_stocks);
        document.getElementById('korea-holdings').textContent = formatNumber(status.korea_holdings);
        document.getElementById('usa-holdings').textContent = formatNumber(status.usa_holdings);

    } catch (error) {
        console.error('시스템 상태 로드 실패:', error);
    }
}

// 로그 로드
async function loadLogs(logType) {
    try {
        const response = await fetch(`/api/dashboard/logs?log_type=${logType}&lines=50`);
        if (!response.ok) throw new Error('로그 로드 실패');

        const logs = await response.json();
        const viewer = document.getElementById('log-viewer');

        if (logs.length === 0) {
            viewer.innerHTML = '<div class="text-center text-gray-400">로그가 없습니다.</div>';
            return;
        }

        viewer.innerHTML = logs.map(line =>
            `<div class="log-line">${escapeHtml(line.trim())}</div>`
        ).join('');

        // 스크롤을 맨 아래로
        viewer.scrollTop = viewer.scrollHeight;

    } catch (error) {
        console.error('로그 로드 실패:', error);
        document.getElementById('log-viewer').innerHTML =
            '<div class="text-center text-red-400">로그를 불러올 수 없습니다.</div>';
    }
}

// HTML 이스케이프
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 토스트 알림 표시
function showToast(message, type = 'error') {
    const container = document.getElementById('toast-container') || createToastContainer();
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <span class="toast-icon">${type === 'error' ? '⚠' : type === 'success' ? '✓' : 'ⓘ'}</span>
        <span class="toast-message">${escapeHtml(message)}</span>
        <button class="toast-close" onclick="this.parentElement.remove()">×</button>
    `;
    container.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

function createToastContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
    return container;
}

function showError(message) {
    console.error(message);
    showToast(message, 'error');
}

function showSuccess(message) {
    showToast(message, 'success');
}

// 종목 검색 (향후 구현)
async function searchStocks(query) {
    try {
        const response = await fetch(`/api/dashboard/stocks/search?query=${encodeURIComponent(query)}`);
        if (!response.ok) throw new Error('종목 검색 실패');

        return await response.json();
    } catch (error) {
        console.error('종목 검색 실패:', error);
        return [];
    }
}

// 가격 히스토리 로드 (향후 차트 구현용)
async function loadPriceHistory(symbol, days = 30) {
    try {
        const response = await fetch(`/api/dashboard/stocks/${symbol}/price-history?days=${days}`);
        if (!response.ok) throw new Error('가격 히스토리 로드 실패');

        return await response.json();
    } catch (error) {
        console.error('가격 히스토리 로드 실패:', error);
        return [];
    }
}
