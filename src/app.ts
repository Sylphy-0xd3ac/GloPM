import Koa from 'koa';
import { koaBody } from 'koa-body';
import helmet from 'koa-helmet';
import logger from 'koa-morgan';
import { connectToMongoDB } from './utils/database';
import { authRoutes } from './routes/authRoutes';
import { packageRoutes } from './routes/packageRoutes';
import { PORT } from './config';

const app = new Koa();

// 增加安全性
app.use(helmet());

// 使用 koa-body 解析 JSON、urlencoded 和 multipart 数据
app.use(
  koaBody({
    multipart: true,
    formidable: {
      keepExtensions: true,
      maxFileSize: 200 * 1024 * 1024, // 设置最大文件大小，例如 200MB
    }
  })
);

// 请求日志
app.use(logger('tiny'));

// 启动服务器
async function startServer() {
  try {
    // 连接到 MongoDB
    const db = await connectToMongoDB();
    
    // 加载路由
    const authRouter = authRoutes(db);
    const packageRouter = packageRoutes(db);

    app.use(authRouter.routes());
    app.use(packageRouter.routes());

    app.listen(PORT, () => {
      console.log(`服务器已启动，端口: ${PORT}`);
    });
  } catch (error) {
    console.error('服务器启动失败:', error);
    process.exit(1);
  }
}

// 启动服务器
startServer();